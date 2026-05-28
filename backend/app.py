import os
import json
import re
import time
import urllib.request
import urllib.error
import hashlib
import threading
from datetime import datetime, timedelta

# Monkeypatch hashlib.md5 for Python 3.8 compatibility with ReportLab
_orig_md5 = hashlib.md5
def _patched_md5(*args, **kwargs):
    kwargs.pop('usedforsecurity', None)
    return _orig_md5(*args, **kwargs)
hashlib.md5 = _patched_md5

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

import db_helper
import audit_apis

# Setup Directories and paths dynamically
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(BACKEND_DIR) == 'backend':
    ROOT_DIR = os.path.dirname(BACKEND_DIR)
else:
    ROOT_DIR = BACKEND_DIR
    BACKEND_DIR = os.path.join(ROOT_DIR, 'backend')

REPORTS_DIR = os.path.join(ROOT_DIR, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

# Override cache file path to be in ROOT_DIR
audit_apis.CACHE_FILE = os.path.join(ROOT_DIR, '.audit_cache.json')

app = Flask(__name__)
CORS(app)

# Initialize database
db_helper.init_db()

def get_safe_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("API Key for Gemini is missing from .env file. Please add it.")
    return key

SETTINGS_FILE = os.path.join(BACKEND_DIR, 'scheduler_settings.json')

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {"interval_minutes": 0, "notify_email": "", "last_scan_time": None}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify(load_settings())

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json
    settings = load_settings()
    settings['interval_minutes'] = float(data.get('interval_minutes', 0))
    settings['notify_email'] = data.get('notify_email', '')
    
    # If enabling for the first time or forcing a reset, we can clear last_scan_time
    # so it triggers soon, but let's keep it simple for now.
    if settings['interval_minutes'] > 0:
        # Reset last scan time so it starts the new schedule cycle from now
        settings['last_scan_time'] = datetime.now().isoformat()
        
    save_settings(settings)
    return jsonify({"ok": True, "settings": settings})

def call_ai(prompt):
    try:
        api_key = get_safe_api_key()
    except Exception as e:
        return f"Authentication error: {str(e)}"
        
    headers = {"Content-Type": "application/json"}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
        
    max_retries = 3
    delay = 1.0
    last_err = None
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=25) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                return res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            last_err = f"HTTP Error {e.code}: {e.reason}"
            if e.code in [429, 502, 503, 504]:
                time.sleep(delay)
                delay *= 2.0
                continue
            else:
                break
        except Exception as e:
            last_err = str(e)
            time.sleep(delay)
            delay *= 2.0
            continue
            
    return f"AI model invocation failed: {last_err}"

def ping_endpoint(url, expected_codes, timeout=8.0):
    start = time.time()
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.getcode()
            latency = int((time.time() - start) * 1000)
            if status_code in expected_codes:
                status = 'warn' if latency > 3000 else 'ok'
                note = 'Slow response — possible performance degradation' if latency > 3000 else ''
            else:
                status = 'error'
                note = f'Unexpected HTTP {status_code} — expected {", ".join(map(str, expected_codes))}'
            return {
                'status': status,
                'http_code': status_code,
                'latency_ms': latency,
                'note': note
            }
    except urllib.error.HTTPError as e:
        status_code = e.code
        latency = int((time.time() - start) * 1000)
        if status_code in expected_codes:
            status = 'warn' if latency > 3000 else 'ok'
            note = 'Slow response — possible performance degradation' if latency > 3000 else ''
        else:
            status = 'error'
            note = f'Unexpected HTTP {status_code} — expected {", ".join(map(str, expected_codes))}'
        return {
            'status': status,
            'http_code': status_code,
            'latency_ms': latency,
            'note': note
        }
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        return {
            'status': 'error',
            'http_code': None,
            'latency_ms': latency,
            'note': f'Network error: {str(e)}'
        }

def run_single_check(service):
    service_id = service['id']
    url = service['url']
    expected_codes_str = service['expected_codes'] or '200'
    
    try:
        expected_codes = [int(c.strip()) for c in expected_codes_str.split(',')]
    except Exception:
        expected_codes = [200]
        
    res = ping_endpoint(url, expected_codes)
    
    conn = db_helper.get_db_connection()
    prev = conn.execute(
        'SELECT status FROM checks WHERE service_id = ? ORDER BY checked_at DESC LIMIT 1',
        (service_id,)
    ).fetchone()
    
    conn.execute(
        'INSERT INTO checks (service_id, status, http_code, latency_ms, note) VALUES (?, ?, ?, ?, ?)',
        (service_id, res['status'], res['http_code'], res['latency_ms'], res['note'])
    )
    
    if prev and prev['status'] != res['status']:
        msg = f"{service['name']} changed from {prev['status']} -> {res['status']}: {res['note']}"
        conn.execute(
            'INSERT INTO alerts (service_id, previous_status, new_status, message) VALUES (?, ?, ?, ?)',
            (service_id, prev['status'], res['status'], msg)
        )
        print(f"[ALERT] {msg}")
        
    conn.commit()
    conn.close()
    return res

# --- Original Legacy Routes ---
@app.route('/api/audit', methods=['POST'])
def run_audit():
    data = request.json
    title = data.get('title', 'Unknown API')
    docsUrl = data.get('docsUrl', '')
    description = data.get('description', '')
    notify_email = data.get('notify_email', '')

    item = {
        "title": title,
        "docsUrl": docsUrl,
        "description": description,
        "notify_email": notify_email
    }

    cache = audit_apis.load_cache()
    clean_name = audit_apis.re.sub(r'[^a-zA-Z0-9]', '_', title.lower())
    current_hash = audit_apis.get_item_hash(item)

    entry = cache.get(clean_name)
    previous_report = entry.get("last_full_report") if entry else None

    try:
        api_key = get_safe_api_key()
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if entry and current_hash == entry.get("input_hash"):
        output_item = item.copy()
        output_item["audit_report"] = "NO_CHANGE"
        pdf_filename = f"{clean_name}_audit_report.pdf"
        pdf_path = os.path.join(REPORTS_DIR, pdf_filename)
        
        if notify_email:
            html_report = audit_apis.generate_html_report([output_item])
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as f:
                    pdf_bytes = f.read()
                audit_apis.send_report_via_email(notify_email, html_report, f"API Audit Report: {title}", is_html=True, attachments=[(pdf_filename, pdf_bytes)])
            else:
                audit_apis.send_report_via_email(notify_email, html_report, f"API Audit Report: {title}", is_html=True)
            
        return jsonify({
            "status": "NO_CHANGE",
            "message": "No changes detected since the last scan (Cache hit).",
            "pdf_url": f"/api/pdf/{pdf_filename}" if os.path.exists(pdf_path) else None
        })

    try:
        audit_res = audit_apis.query_gemini_search(api_key, item, previous_report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    is_no_change = False
    if previous_report and "NO_CHANGE_DETECTED" in audit_res:
        is_no_change = True
    elif previous_report:
        import difflib
        similarity = difflib.SequenceMatcher(None, previous_report, audit_res.strip()).ratio()
        if similarity > 0.85:
            is_no_change = True

    output_item = item.copy()
    if is_no_change:
        output_item["audit_report"] = "NO_CHANGE"
        cache[clean_name] = {
            "input_hash": current_hash,
            "last_scanned": datetime.now().isoformat(),
            "last_full_report": previous_report
        }
    else:
        try:
            output_item["audit_report"] = json.loads(audit_res)
        except json.JSONDecodeError:
            try:
                fixed_res = audit_apis.re.sub(r'\}\s*\}$', ']\n}', audit_res.strip())
                output_item["audit_report"] = json.loads(fixed_res)
            except Exception:
                output_item["audit_report"] = audit_apis.parse_malformed_json_to_dict(audit_res)
        except Exception:
            output_item["audit_report"] = audit_apis.parse_malformed_json_to_dict(audit_res)

        cache[clean_name] = {
            "input_hash": current_hash,
            "last_scanned": datetime.now().isoformat(),
            "last_full_report": audit_res.strip()
        }
        
    audit_apis.save_cache(cache)
    pdf_filename = f"{clean_name}_audit_report.pdf"
    pdf_path = os.path.join(REPORTS_DIR, pdf_filename)
    
    if notify_email:
        html_report = audit_apis.generate_html_report([output_item])
        pdf_bytes = audit_apis.generate_pdf_report([output_item], pdf_path)
        audit_apis.send_report_via_email(
            notify_email,
            html_report,
            f"API Audit Report: {title}",
            is_html=True,
            attachments=[(pdf_filename, pdf_bytes)]
        )
    else:
        audit_apis.generate_pdf_report([output_item], pdf_path)
        
    return jsonify({
        "status": "SUCCESS",
        "result": output_item,
        "pdf_url": f"/api/pdf/{pdf_filename}"
    })

@app.route('/api/pdf/<filename>')
def serve_pdf(filename):
    safe_filename = os.path.basename(filename)
    full_path = os.path.join(REPORTS_DIR, safe_filename)
    if os.path.exists(full_path):
        return send_file(full_path, mimetype='application/pdf')
    return "File not found", 404


@app.route('/api/quickadd', methods=['GET'])
def get_quickadd_list():
    input_json_path = os.path.join(ROOT_DIR, 'input.json')
    if not os.path.exists(input_json_path):
        input_json_path = os.path.join(os.path.dirname(__file__), 'input.json')
    if not os.path.exists(input_json_path):
        return jsonify([])
    try:
        with open(input_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        mapped = []
        for item in data:
            name = item.get('title', 'Unknown API')
            url = item.get('docsUrl', '')
            description = item.get('description', '')
            notify_email = item.get('notify_email', '')
            name_lower = name.lower()
            if any(x in name_lower for x in ['paypal', 'stripe', 'razorpay', 'payu', 'checkout', 'authorize', 'amazon']):
                tag = 'payments'
            elif any(x in name_lower for x in ['sms', 'twilio', 'clickatell', 'mvaayoo', 'horizon', 'slack']):
                tag = 'messaging'
            elif any(x in name_lower for x in ['email', 'mailtrap', 'sendgrid']):
                tag = 'email'
            elif any(x in name_lower for x in ['chart', 'vector', 'layout', 'resumable', 'lightbox', 'masonry', 'flowplayer', 'wizard', 'toastr', 'dompdf', 'emogrifier', 'fpdi', 'fpdf']):
                tag = 'devtools'
            else:
                tag = 'custom'
            mapped.append({
                'name': name,
                'url': url,
                'expected_codes': '200,301,302',
                'tag': tag,
                'description': description,
                'notify_email': notify_email
            })
        return jsonify(mapped)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- New Monitor Dashboard Routes ---
@app.route('/api/services', methods=['GET'])
def get_services():
    conn = db_helper.get_db_connection()
    services = conn.execute('SELECT * FROM services WHERE active = 1 ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(s) for s in services])

@app.route('/api/services', methods=['POST'])
def add_service():
    data = request.json
    name = data.get('name')
    url = data.get('url')
    expected_codes = data.get('expected_codes', '200')
    tag = data.get('tag', 'custom')
    description = data.get('description', '')
    notify_email = data.get('notify_email', '')
    
    if not name or not url:
        return jsonify({'ok': False, 'error': 'name and url are required'}), 400
        
    service_id = db_helper.execute_db(
        'INSERT INTO services (name, url, expected_codes, tag, description, notify_email) VALUES (?, ?, ?, ?, ?, ?)',
        (name, url, expected_codes, tag, description, notify_email)
    )
    
    # Immediate ping check disabled based on user preference
    # Services will only be scanned manually when clicking 'Run All Checks'
        
    return jsonify({
        'ok': True,
        'id': service_id,
        'name': name,
        'url': url,
        'expected_codes': expected_codes,
        'tag': tag,
        'description': description,
        'notify_email': notify_email
    })

@app.route('/api/services/<int:id>', methods=['DELETE'])
def delete_service(id):
    db_helper.execute_db('UPDATE services SET active = 0 WHERE id = ?', (id,))
    return jsonify({'ok': True})

@app.route('/api/services/<int:id>', methods=['PATCH'])
def update_service(id):
    data = request.json
    name = data.get('name')
    url = data.get('url')
    expected_codes = data.get('expected_codes')
    tag = data.get('tag')
    
    conn = db_helper.get_db_connection()
    svc = conn.execute('SELECT * FROM services WHERE id = ?', (id,)).fetchone()
    if not svc:
        conn.close()
        return jsonify({'ok': False, 'error': 'Service not found'}), 404
        
    conn.execute(
        'UPDATE services SET name=?, url=?, expected_codes=?, tag=? WHERE id=?',
        (name or svc['name'], url or svc['url'], expected_codes or svc['expected_codes'], tag or svc['tag'], id)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/check/all', methods=['POST'])
def run_all_checks():
    conn = db_helper.get_db_connection()
    services = conn.execute('SELECT * FROM services WHERE active = 1').fetchall()
    conn.close()
    
    results = []
    for svc in services:
        res = run_single_check(dict(svc))
        results.append({'service': svc['name'], **res})
        
    return jsonify({'ok': True, 'results': results})

@app.route('/api/check/<int:id>', methods=['POST'])
def run_single_check_route(id):
    conn = db_helper.get_db_connection()
    svc = conn.execute('SELECT * FROM services WHERE id = ? AND active = 1', (id,)).fetchone()
    conn.close()
    
    if not svc:
        return jsonify({'ok': False, 'error': 'Service not found'}), 404
        
    res = run_single_check(dict(svc))
    return jsonify({'ok': True, 'service': svc['name'], **res})

@app.route('/api/summary', methods=['GET'])
def get_summary():
    conn = db_helper.get_db_connection()
    services = conn.execute('SELECT * FROM services WHERE active = 1 ORDER BY id DESC').fetchall()
    
    summary_list = []
    counts = {'total': len(services), 'ok': 0, 'warn': 0, 'error': 0, 'idle': 0}
    
    for s in services:
        latest = conn.execute(
            'SELECT * FROM checks WHERE service_id = ? ORDER BY checked_at DESC LIMIT 1',
            (s['id'],)
        ).fetchone()
        
        svc_dict = dict(s)
        if latest:
            svc_dict['latest'] = dict(latest)
            status = latest['status']
            counts[status] = counts.get(status, 0) + 1
        else:
            svc_dict['latest'] = None
            counts['idle'] += 1
        summary_list.append(svc_dict)
            
    conn.close()
    return jsonify({
        'services': summary_list,
        'counts': counts
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = request.args.get('limit', default=10, type=int)
    conn = db_helper.get_db_connection()
    checks = conn.execute('''
        SELECT c.*, s.name as service_name 
        FROM checks c 
        JOIN services s ON c.service_id = s.id 
        ORDER BY c.checked_at DESC 
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in checks])

# --- AI Diagnostics and Fixes ---
@app.route('/api/ai/diagnose', methods=['POST'])
def diagnose_api():
    data = request.json
    service_id = data.get('service_id')
    
    conn = db_helper.get_db_connection()
    svc = conn.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
    latest_check = conn.execute('SELECT * FROM checks WHERE service_id = ? ORDER BY checked_at DESC LIMIT 1', (service_id,)).fetchone()
    conn.close()
    
    if not svc:
        return jsonify({'error': 'Service not found'}), 404
        
    status = latest_check['status'] if latest_check else 'not checked'
    http_code = latest_check['http_code'] if latest_check else 'N/A'
    latency = latest_check['latency_ms'] if latest_check else 'N/A'
    note = latest_check['note'] if latest_check else ''
    
    prompt = f"""
    You are an expert API developer and debugger. Please diagnose the following service status.
    
    Service Name: {svc['name']}
    Endpoint URL: {svc['url']}
    Expected HTTP Codes: {svc['expected_codes']}
    Current Status: {status}
    HTTP Code Returned: {http_code}
    Latency: {latency}ms
    System Note: {note}
    
    Provide:
    1. ROOT CAUSE Analysis: (1-2 sentences explaining what is wrong based on standard conventions for this API provider or HTTP protocol)
    2. ERROR CATEGORY: (Specify one: breaking change, authorization, rate limit, deprecation, or server outage)
    3. RECOMMENDED RESOLUTION: (Actionable steps to fix this error)
    4. SYSTEM RISK LEVEL: (Low, Medium, or High)
    
    Return plain text only, keep it concise, and address the developer directly. Do not use Markdown code blocks.
    """
    
    response = call_ai(prompt)
    return jsonify({'result': response})

@app.route('/api/ai/suggest_fix', methods=['POST'])
def suggest_fix_api():
    data = request.json
    service_id = data.get('service_id')
    
    conn = db_helper.get_db_connection()
    svc = conn.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
    latest_check = conn.execute('SELECT * FROM checks WHERE service_id = ? ORDER BY checked_at DESC LIMIT 1', (service_id,)).fetchone()
    conn.close()
    
    if not svc:
        return jsonify({'error': 'Service not found'}), 404
        
    prompt = f"""
    Generate three concrete, specific debugging steps to fix the failing integration below:
    
    Service Name: {svc['name']}
    Endpoint URL: {svc['url']}
    Expected HTTP Codes: {svc['expected_codes']}
    Latest HTTP status: {latest_check['http_code'] if latest_check else 'none'}
    System Note: {latest_check['note'] if latest_check else ''}
    
    Suggest detailed steps including documentation links (if standard for {svc['name']}), auth headers validation, API versioning verification, and fallback suggestions.
    
    Return plain text only, keep it concise, and format it as 3 distinct numbered bullet points.
    """
    
    response = call_ai(prompt)
    return jsonify({'result': response})

@app.route('/api/ai/full_report', methods=['POST'])
def full_report_api():
    data = request.json
    service_id = data.get('service_id')
    
    conn = db_helper.get_db_connection()
    svc = conn.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
    conn.close()
    
    if not svc:
        return jsonify({'error': 'Service not found'}), 404
        
    # Build standard audit input format and call the main auditor pipeline
    title = svc['name']
    docsUrl = svc['url']
    description = svc['description'] if svc['description'] else f"Monitored API service tag: {svc['tag']}. Expected HTTP codes: {svc['expected_codes']}."
    notify_email = svc['notify_email'] if svc['notify_email'] else ""
    
    # Trigger audit_apis logic as in /api/audit
    item = {
        "title": title,
        "docsUrl": docsUrl,
        "description": description,
        "notify_email": notify_email
    }
    
    cache = audit_apis.load_cache()
    clean_name = audit_apis.re.sub(r'[^a-zA-Z0-9]', '_', title.lower())
    current_hash = audit_apis.get_item_hash(item)
    
    entry = cache.get(clean_name)
    previous_report = entry.get("last_full_report") if entry else None
    
    pdf_filename = f"{clean_name}_audit_report.pdf"
    pdf_path = os.path.join(REPORTS_DIR, pdf_filename)
    
    try:
        api_key = get_safe_api_key()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
        
    try:
        audit_res = audit_apis.query_gemini_search(api_key, item, previous_report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
    is_no_change = False
    if previous_report and "NO_CHANGE_DETECTED" in audit_res:
        is_no_change = True
    elif previous_report:
        import difflib
        similarity = difflib.SequenceMatcher(None, previous_report, audit_res.strip()).ratio()
        if similarity > 0.85:
            is_no_change = True
            
    output_item = item.copy()
    if is_no_change:
        output_item["audit_report"] = "NO_CHANGE"
        output_item["title"] = f"{title} (No Changes)"
        cache[clean_name] = {
            "input_hash": current_hash,
            "last_scanned": datetime.now().isoformat(),
            "last_full_report": previous_report
        }
    else:
        try:
            output_item["audit_report"] = json.loads(audit_res)
        except json.JSONDecodeError:
            try:
                fixed_res = audit_apis.re.sub(r'\}\s*\}$', ']\n}', audit_res.strip())
                output_item["audit_report"] = json.loads(fixed_res)
            except Exception:
                output_item["audit_report"] = audit_apis.parse_malformed_json_to_dict(audit_res)
        except Exception:
            output_item["audit_report"] = audit_apis.parse_malformed_json_to_dict(audit_res)
            
        cache[clean_name] = {
            "input_hash": current_hash,
            "last_scanned": datetime.now().isoformat(),
            "last_full_report": audit_res.strip()
        }
        
    audit_apis.save_cache(cache)
    
    if not is_no_change or not os.path.exists(pdf_path):
        audit_apis.generate_pdf_report([output_item], pdf_path)
        
    if notify_email:
        html_report = audit_apis.generate_html_report([output_item])
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            audit_apis.send_report_via_email(notify_email, html_report, f"API Audit Report: {title}", is_html=True, attachments=[(pdf_filename, pdf_bytes)])
        else:
            audit_apis.send_report_via_email(notify_email, html_report, f"API Audit Report: {title}", is_html=True)
    
    if is_no_change:
        return jsonify({
            "status": "NO_CHANGE",
            "message": f"AI Audit Complete.\nNo updates detected for {title} since the last scan.\nServing previous compiled report.",
            "result": output_item,
            "pdf_url": f"/api/pdf/{pdf_filename}"
        })
    else:
        return jsonify({
            "status": "SUCCESS",
            "result": output_item,
            "pdf_url": f"/api/pdf/{pdf_filename}"
        })


def background_check_loop():
    time.sleep(5)
    while True:
        try:
            settings = load_settings()
            interval_minutes = settings.get("interval_minutes", 0)
            notify_email = settings.get("notify_email", "")
            
            if interval_minutes > 0:
                last_scan_str = settings.get("last_scan_time")
                run_scan = False
                
                if not last_scan_str:
                    run_scan = True
                else:
                    last_scan = datetime.fromisoformat(last_scan_str)
                    if datetime.now() - last_scan >= timedelta(minutes=interval_minutes):
                        run_scan = True
                        
                if run_scan:
                    print(f"[{datetime.now()}] Running scheduled API scan...")
                    conn = db_helper.get_db_connection()
                    services = conn.execute('SELECT * FROM services WHERE active = 1').fetchall()
                    conn.close()
                    
                    results = []
                    for svc in services:
                        try:
                            res = run_single_check(dict(svc))
                            results.append({'service': svc['name'], **res})
                        except Exception as ex:
                            print(f"Error checking service {svc['name']}: {ex}")
                            
                    settings['last_scan_time'] = datetime.now().isoformat()
                    save_settings(settings)
                    
                    if notify_email and results:
                        errors = [r for r in results if r['status'] == 'error']
                        warns = [r for r in results if r['status'] == 'warn']
                        oks = [r for r in results if r['status'] == 'ok']
                        
                        html = f"<html><body style='font-family: Arial, sans-serif;'>"
                        html += f"<h2>Automated API Scan Summary</h2>"
                        html += f"<p>Total Scanned: <b>{len(results)}</b> | OK: <b>{len(oks)}</b> | Warnings: <b>{len(warns)}</b> | Errors: <b>{len(errors)}</b></p><hr>"
                        
                        if errors or warns:
                            html += "<h3>Issues Detected:</h3><ul>"
                            for api in errors + warns:
                                color = "red" if api['status'] == 'error' else "orange"
                                html += f"<li style='margin-bottom: 10px;'><span style='color:{color}; font-weight:bold;'>[{api['status'].upper()}]</span> <b>{api['service']}</b><br/>HTTP: {api['http_code']} | Latency: {api['latency_ms']}ms<br/>Note: <i>{api['note']}</i></li>"
                            html += "</ul>"
                        else:
                            html += "<p style='color:green;'>All APIs are Healthy! No action required.</p>"
                        html += "</body></html>"
                        
                        audit_apis.send_report_via_email(
                            notify_email, 
                            html, 
                            f"Auto-Scan Report: {len(errors)} Errors, {len(warns)} Warnings", 
                            is_html=True
                        )
        except Exception as e:
            print(f"Error in background check loop: {e}")
        time.sleep(60)

checker_thread = threading.Thread(target=background_check_loop, daemon=True)
checker_thread.start()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
