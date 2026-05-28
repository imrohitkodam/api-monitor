#!/usr/bin/env python3
# flake8: noqa: E501, W293, E303
import os
import sys
import json
import urllib.request
import urllib.error
import time
import hashlib
import re
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import html

# Load .env variables without needing extra libraries
if os.path.exists('.env'):
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('=', 1)
                if len(parts) == 2:
                    os.environ.setdefault(parts[0].strip(), parts[1].strip().strip("'\""))

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
except ImportError:
    pass

# ANSI Escape Codes for Premium UI Aesthetics
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

JSON_INPUT = "input.json"
MARKDOWN_OUTPUT = "api_diagnostic_audit.md"
CACHE_FILE = ".audit_cache.json"


def get_gemini_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print(f"{RED}Error: GEMINI_API_KEY is missing from .env file.{RESET}")
        sys.exit(1)
    return key


def parse_integrations(file_path):
    if not os.path.exists(file_path):
        print(
            f"{RED}Error: {file_path} not found. Please create {file_path} in this directory.{RESET}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            # Ensure it is a list
            if isinstance(data, dict):
                data = [data]
            return data
        except Exception as e:
            print(f"{RED}Error parsing JSON: {str(e)}{RESET}")
            sys.exit(1)


def get_item_hash(item):
    # Hash the dictionary to detect if the user changed the input JSON fields
    hash_item = item.copy()
    hash_item.pop("notify_email", None)
    hash_item.pop("notifyEmail", None)
    return hashlib.md5(
        json.dumps(
            hash_item,
            sort_keys=True).encode('utf-8')).hexdigest()


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def query_gemini_fallback(url, headers, payload):
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST")
            time.sleep(6)
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return text
        except Exception as e:
            if attempt < 3:
                print(f"{YELLOW}Fallback audit error ({str(e)}). Retrying...{RESET}")
                time.sleep(10)
                continue
            print(f"{RED}Fallback audit failed permanently: {str(e)}{RESET}")
            return f"Error: Unable to generate audit even with internal knowledge fallback ({str(e)})."
    return "Error: Unexpected fallback failure."


def query_gemini_search(api_key, integration, previous_report=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

    title = integration.get("title", "Unknown API")
    docsUrl = integration.get("docsUrl", "No URL provided")
    description = integration.get("description", "No description provided")

    prompt = f"""
    You are an expert API and security consultant. Search the web and use your developer knowledge to audit the following technology: {title}.
    The user provided the following documentation URL they might be using: {docsUrl}.
    The user provided this description of their current usage/knowledge: "{description}"

    Note: You do NOT have access to the user's actual codebase. The user might not even know exactly what version they are using.

    Based on the information provided and a live documentation search, provide a highly detailed diagnostic report.
    You MUST return your entire response as a single, valid, raw JSON object (without Markdown code blocks). Use the following exact JSON structure:

    {{
      "executive_summary": {{
        "change_summary": "What exactly changed? (1-2 sentences summary of findings)",
        "seriousness": "High/Medium/Low risk",
        "grace_period_days": "Number of days (or approx time) before it completely breaks or is deprecated, e.g., '120 days' or 'Already dead'",
        "old_vs_new": "What was the old behavior/version vs what it should be now."
      }},
      "global_state": {{
        "latest_official_release": "What is the absolute latest, recommended standard API/SDK for this platform? e.g. REST API v2 using Webhooks",
        "recent_deprecations": ["List any major versions, endpoints, or SDKs that have been killed off or deprecated in recent years"]
      }},
      "diagnostic_guide": [
        "Since we cannot see the user's code, provide bullet points telling the user exactly what to look for in their codebase to determine their version.",
        "Example: If your code uses `svcs.paypal.com/AdaptivePayments`, you are using a dead API."
      ],
      "migration_path": "Provide a high-level summary of how one transitions from the legacy systems to the latest standard.",
      "estimated_lifespan_and_risks": [
        "What breaks if they are on the old versions?",
        "Security or operational risks."
      ],
      "future_outlook": "Are there any upcoming changes, major versions, or deprecations planned for the future? What should the developer prepare for in the next 1-2 years?"
    }}
    """

    if previous_report:
        prompt += f"""

    ### CRITICAL INSTRUCTION:
    We previously ran this audit and generated the following JSON report:
    ---
    {previous_report}
    ---
    Please compare your new findings with the previous report above.
    If there are absolutely no new updates, version changes, deprecation notices, or migration recommendations since that previous report, you MUST output ONLY the exact string:
    NO_CHANGE_DETECTED
    Do not output the full JSON if nothing changed. Only output the full JSON if there is new information or the user's description changed.
    """

    payload_search = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"googleSearch": {}}]
    }

    payload_no_search = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    headers = {"Content-Type": "application/json"}
    max_retries = 5
    backoff = 12

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload_search).encode("utf-8"),
            headers=headers,
            method="POST")
        try:
            time.sleep(6)
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                try:
                    text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    cleaned = text.strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[7:]
                    elif cleaned.startswith("```"):
                        cleaned = cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    return cleaned.strip()
                except (KeyError, IndexError):
                    print(
                        f"{YELLOW}Search grounding throttled or empty for {title}. Falling back to internal knowledge audit...{RESET}")
                    return query_gemini_fallback(
                        url, headers, payload_no_search)
        except urllib.error.HTTPError as e:
            if e.code in [429, 500, 502, 503, 504]:
                print(
                    f"{YELLOW}API Error ({e.code}). Retrying attempt {attempt}/{max_retries} after sleeping {backoff} seconds...{RESET}")
                time.sleep(backoff)
                backoff *= 1.5
                continue
            print(f"{RED}HTTP Error during query: {e.code} - {e.reason}{RESET}")
            break
        except Exception as e:
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                print(
                    f"{YELLOW}Timeout Error. Retrying attempt {attempt}/{max_retries} after sleeping {backoff} seconds...{RESET}")
                time.sleep(backoff)
                backoff *= 1.5
                continue
            print(
                f"{RED}Exception during search query: {str(e)}. Falling back to internal knowledge audit...{RESET}")
            return query_gemini_fallback(url, headers, payload_no_search)

    print(f"{YELLOW}Search queries failed. Triggering internal knowledge audit fallback...{RESET}")
    fallback_text = query_gemini_fallback(url, headers, payload_no_search)
    try:
        # Strip potential markdown json formatting block if the model ignores
        # the instruction
        cleaned = fallback_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()
    except Exception:
        return fallback_text


def generate_text_report(output_data):
    report_lines = []
    for item in output_data:
        report_lines.append(
            f"=== API AUDIT REPORT: {item.get('title', 'Unknown')} ===")
        report_lines.append(f"Docs URL: {item.get('docsUrl', 'N/A')}")
        report_lines.append(f"Description: {item.get('description', 'N/A')}")
        report_lines.append("")

        audit = item.get("audit_report", {})
        if isinstance(audit, dict):
            # Executive Summary
            summary = audit.get("executive_summary")
            if summary:
                report_lines.append("--- EXECUTIVE SUMMARY ---")
                report_lines.append(f"Change Summary: {summary.get('change_summary', 'N/A')}")
                report_lines.append(f"Seriousness: {summary.get('seriousness', 'N/A')}")
                report_lines.append(f"Grace Period: {summary.get('grace_period_days', 'N/A')}")
                report_lines.append(f"Old vs New: {summary.get('old_vs_new', 'N/A')}")
                report_lines.append("")

            # Global State
            global_state = audit.get("global_state", {})
            report_lines.append("--- GLOBAL STATE ---")
            report_lines.append(
                f"Latest Official Release: {global_state.get('latest_official_release', 'N/A')}")
            report_lines.append("Recent Deprecations:")
            for dep in global_state.get("recent_deprecations", []):
                report_lines.append(f" {dep}")
            report_lines.append("")

            # Diagnostic Guide
            report_lines.append("--- DIAGNOSTIC GUIDE ---")
            for guide in audit.get("diagnostic_guide", []):
                report_lines.append(f" {guide}")
            report_lines.append("")

            # Migration Path
            report_lines.append("--- MIGRATION PATH ---")
            report_lines.append(audit.get("migration_path", "N/A"))
            report_lines.append("")

            # Estimated Lifespan and Risks
            report_lines.append("--- ESTIMATED LIFESPAN AND RISKS ---")
            for risk in audit.get("estimated_lifespan_and_risks", []):
                report_lines.append(f" {risk}")
            report_lines.append("")

            # Future Outlook
            report_lines.append("--- FUTURE OUTLOOK (UPCOMING CHANGES) ---")
            report_lines.append(audit.get("future_outlook", "No upcoming changes detected."))
            report_lines.append("")
        else:
            if audit == "NO_CHANGE":
                report_lines.append("--- AUDIT STATUS ---")
                report_lines.append("NO changes detected since the last scan.")
                report_lines.append("")
            else:
                report_lines.append("--- RAW AUDIT REPORT ---")
                report_lines.append(str(audit))
                report_lines.append("")

        report_lines.append(
            "==================================================\n")
    return "\n".join(report_lines)


def generate_html_report(output_data):
    html = [
        "<html>",
        "<head><style>",
        "body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f9fafb; margin: 0; padding: 20px; color: #333; }",
        ".container { max-width: 800px; margin: 0 auto; background: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); overflow: hidden; }",
        ".header { background-color: #1e3a8a; color: white; padding: 20px 30px; text-align: center; }",
        ".header h1 { margin: 0; font-size: 24px; }",
        ".content { padding: 30px; }",
        ".summary-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin-bottom: 20px; background-color: #fbfbfc; border-left: 4px solid #3b82f6; }",
        ".summary-card h2 { margin-top: 0; color: #1e40af; font-size: 20px; margin-bottom: 10px; }",
        ".badge-cache { display: inline-block; background-color: #10b981; color: white; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: bold; margin-bottom: 10px; }",
        ".badge-new { display: inline-block; background-color: #f59e0b; color: white; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: bold; margin-bottom: 10px; }",
        ".snippet { font-size: 14px; color: #4b5563; line-height: 1.5; margin-bottom: 15px; }",
        ".btn { display: inline-block; background-color: #3b82f6; color: white; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 14px; font-weight: 500; }",
        ".details-section { margin-top: 50px; border-top: 2px dashed #e5e7eb; padding-top: 30px; }",
        ".detail-block { margin-bottom: 40px; }",
        ".detail-block h3 { color: #1e3a8a; font-size: 22px; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }",
        ".section-title { font-weight: bold; color: #374151; margin-top: 15px; text-transform: uppercase; font-size: 13px; letter-spacing: 0.05em; }",
        "ul { padding-left: 20px; margin-top: 5px; }",
        "li { margin-bottom: 8px; font-size: 14px; line-height: 1.5; }",
        ".raw-json { background-color: #1f2937; color: #f3f4f6; padding: 15px; border-radius: 6px; font-family: monospace; white-space: pre-wrap; font-size: 13px; overflow-x: auto; }",
        "</style></head>",
        "<body>",
        "<div class='container'>",
        "<div class='header'><h1>API Diagnostic Audit Report</h1></div>",
        "<div class='content'>"]

    html.append(
        "<h2 style='color: #111827; margin-bottom: 20px;'>Audit Summary</h2>")
    for idx, item in enumerate(output_data):
        title = item.get("title", "Unknown API")
        audit = item.get("audit_report", {})
        

        html.append("<div class='summary-card'>")
        html.append(f"<h2>{title}</h2>")

        if audit == "NO_CHANGE":
            html.append("<span class='badge-cache'>No Changes Detected</span>")
            html.append(
                "<p class='snippet'>This API configuration has not changed since the last audit. The previous findings remain valid.</p>")
        else:
            html.append("<span class='badge-new'>New Report Generated</span>")
            snippet = "New diagnostic data is available for this API."
            if isinstance(audit, dict):
                global_state = audit.get("global_state", {})
                latest_release = global_state.get(
                    "latest_official_release", "")
                if latest_release:
                    snippet = latest_release[:150] + "..." if len(
                        latest_release) > 150 else latest_release
            html.append(
                f"<p class='snippet'><strong>Latest State:</strong> {snippet}</p>")

        html.append("</div>")

    html.append("</div></div></body></html>")
    return "\n".join(html)


def generate_pdf_report(output_data, filename):
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    Story = []

    title_style = styles['Heading1']
    subtitle_style = styles['Heading2']
    subtitle_style.spaceBefore = 12
    subtitle_style.spaceAfter = 6

    normal_style = styles['Normal']
    normal_style.spaceBefore = 4
    normal_style.spaceAfter = 4

    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        leftIndent=20,
        spaceBefore=3,
        spaceAfter=3,
        bulletIndent=10
    )

    def fmt(text):
        text = str(text)
        text = html.escape(text)
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', text)
        return text

    for item in output_data:
        title = item.get('title', 'Unknown API')
        Story.append(
            Paragraph(
                f"API AUDIT REPORT: {html.escape(title)}",
                title_style))
        Story.append(Spacer(1, 8))

        Story.append(
            Paragraph(
                f"<b>Docs URL:</b> {fmt(item.get('docsUrl', 'N/A'))}",
                normal_style))
        Story.append(
            Paragraph(
                f"<b>Description:</b> {fmt(item.get('description', 'N/A'))}",
                normal_style))
        Story.append(Spacer(1, 12))

        audit = item.get("audit_report", {})
        if isinstance(audit, dict):
            summary = audit.get("executive_summary")
            if summary:
                Story.append(Paragraph("EXECUTIVE SUMMARY", subtitle_style))
                Story.append(Paragraph(f"<b>Change Summary:</b> {fmt(summary.get('change_summary', 'N/A'))}", normal_style))
                Story.append(Paragraph(f"<b>Seriousness:</b> {fmt(summary.get('seriousness', 'N/A'))}", normal_style))
                Story.append(Paragraph(f"<b>Grace Period:</b> {fmt(summary.get('grace_period_days', 'N/A'))}", normal_style))
                Story.append(Paragraph(f"<b>Old vs New:</b> {fmt(summary.get('old_vs_new', 'N/A'))}", normal_style))
                Story.append(PageBreak())

            Story.append(Paragraph("GLOBAL STATE", subtitle_style))
            global_state = audit.get("global_state", {})
            Story.append(
                Paragraph(
                    f"<b>Latest Official Release:</b> {fmt(global_state.get('latest_official_release', 'N/A'))}",
                    normal_style))

            deps = global_state.get("recent_deprecations", [])
            if deps:
                Story.append(
                    Paragraph(
                        "<b>Recent Deprecations:</b>",
                        normal_style))
                for dep in deps:
                    Story.append(
                        Paragraph(
                            f"<bullet>&bull;</bullet> {fmt(dep)}",
                            bullet_style))
            Story.append(Spacer(1, 6))

            guides = audit.get("diagnostic_guide", [])
            if guides:
                Story.append(Paragraph("DIAGNOSTIC GUIDE", subtitle_style))
                for guide in guides:
                    Story.append(
                        Paragraph(
                            f"<bullet>&bull;</bullet> {fmt(guide)}",
                            bullet_style))
                Story.append(Spacer(1, 6))

            path = audit.get("migration_path", "")
            if path:
                Story.append(Paragraph("MIGRATION PATH", subtitle_style))
                Story.append(Paragraph(fmt(path), normal_style))
                Story.append(Spacer(1, 6))

            risks = audit.get("estimated_lifespan_and_risks", [])
            if risks:
                Story.append(
                    Paragraph(
                        "ESTIMATED LIFESPAN AND RISKS",
                        subtitle_style))
                for risk in risks:
                    Story.append(
                        Paragraph(
                            f"<bullet>&bull;</bullet> {fmt(risk)}",
                            bullet_style))
                Story.append(Spacer(1, 6))
                
            future = audit.get("future_outlook", "")
            if future:
                Story.append(Paragraph("FUTURE OUTLOOK (UPCOMING CHANGES)", subtitle_style))
                Story.append(Paragraph(fmt(future), normal_style))
                Story.append(Spacer(1, 6))
        else:
            if audit == "NO_CHANGE":
                Story.append(Paragraph("AUDIT STATUS", subtitle_style))
                Story.append(
                    Paragraph(
                        "NO changes detected since the last scan.",
                        normal_style))
                Story.append(Spacer(1, 12))
            else:
                Story.append(Paragraph("RAW AUDIT REPORT", subtitle_style))
                Story.append(Paragraph(fmt(audit), normal_style))
                Story.append(Spacer(1, 12))

        Story.append(Spacer(1, 24))

    doc.build(Story)
    with open(filename, 'rb') as f:
        pdf_bytes = f.read()
    return pdf_bytes


def send_report_via_email(
        recipient_email,
        report_content,
        subject="Autonomous API Diagnostic Audit Report",
        is_html=False,
        attachments=None):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        print(f"{YELLOW}Warning: SMTP_USER and SMTP_PASS environment variables not set in .env. Cannot send email.{RESET}")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient_email
        msg['Subject'] = subject

        if is_html:
            msg.attach(MIMEText(report_content, 'html'))
        else:
            msg.attach(
                MIMEText(
                    "Hello,\n\nPlease find the generated API Diagnostic Audit report below:\n\n" +
                    report_content,
                    'plain'))

        if attachments:
            for filename, file_content in attachments:
                part = MIMEBase('application', 'octet-stream')
                if isinstance(file_content, str):
                    part.set_payload(file_content.encode('utf-8'))
                else:
                    part.set_payload(file_content)
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"')
                msg.attach(part)

        print(f"\n{GREEN}Sending email to {recipient_email}...{RESET}")
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()

        print(f"{GREEN}Successfully sent audit report to {recipient_email}{RESET}")
    except Exception as e:
        print(f"{RED}Failed to send email: {str(e)}{RESET}")


def parse_malformed_json_to_dict(text):
    result = {
        "executive_summary": {
            "change_summary": "N/A",
            "seriousness": "N/A",
            "grace_period_days": "N/A",
            "old_vs_new": "N/A"
        },
        "global_state": {
            "latest_official_release": "N/A",
            "recent_deprecations": []
        },
        "diagnostic_guide": [],
        "migration_path": "N/A",
        "estimated_lifespan_and_risks": [],
        "future_outlook": "N/A"
    }

    m = re.search(r'"change_summary"\s*:\s*"((?:\\.|[^"\\])*)"', text, re.DOTALL)
    if m: result["executive_summary"]["change_summary"] = m.group(1).replace('\\"', '"')
    m = re.search(r'"seriousness"\s*:\s*"((?:\\.|[^"\\])*)"', text, re.DOTALL)
    if m: result["executive_summary"]["seriousness"] = m.group(1).replace('\\"', '"')
    m = re.search(r'"grace_period_days"\s*:\s*"((?:\\.|[^"\\])*)"', text, re.DOTALL)
    if m: result["executive_summary"]["grace_period_days"] = m.group(1).replace('\\"', '"')
    m = re.search(r'"old_vs_new"\s*:\s*"((?:\\.|[^"\\])*)"', text, re.DOTALL)
    if m: result["executive_summary"]["old_vs_new"] = m.group(1).replace('\\"', '"')

    m = re.search(
        r'"migration_path"\s*:\s*"((?:\\.|[^"\\])*)"',
        text,
        re.DOTALL)
    if m:
        result["migration_path"] = m.group(1).replace('\\"', '"')
    m = re.search(r'"latest_official_release"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if m:
        result["global_state"]["latest_official_release"] = m.group(
            1).replace('\\"', '"')
    m = re.search(r'"future_outlook"\s*:\s*"((?:\\.|[^"\\])*)"', text, re.DOTALL)
    if m:
        result["future_outlook"] = m.group(1).replace('\\"', '"')
    for key in [
        "recent_deprecations",
        "diagnostic_guide",
            "estimated_lifespan_and_risks"]:
        m = re.search(f'"{key}"\\s*:\\s*\\[([^\\]]*)\\]', text, re.DOTALL)
        if m:
            items = []
            for item_match in re.finditer(r'"((?:\\.|[^"\\])*)"', m.group(1)):
                items.append(item_match.group(1).replace('\\"', '"'))
            if key == "recent_deprecations":
                result["global_state"]["recent_deprecations"] = items
            else:
                result[key] = items
    return result


def main():
    print(f"{BLUE}===================================================={RESET}")
    print(f"{BLUE} Isolated API Diagnostic Auditor (JSON Input){RESET}")
    print(f"{BLUE}===================================================={RESET}")

    # Parse CLI flags
    is_cron = "--cron" in sys.argv or "--all" in sys.argv or "-a" in sys.argv
    force_scan = "--force" in sys.argv or "-f" in sys.argv

    api_key = get_gemini_api_key()
    print(f"{BLUE}>>> Using Gemini AI Model <<<{RESET}")

    print(f"\n{GREEN}[1/3] Parsing integrations from {JSON_INPUT}...{RESET}")
    integrations = parse_integrations(JSON_INPUT)
    print(f"Successfully loaded {len(integrations)} integrations.\n")

    email_recipient = None
    if "--email" in sys.argv:
        try:
            idx = sys.argv.index("--email")
            email_recipient = sys.argv[idx + 1]
        except (ValueError, IndexError):
            pass

    first_n = None
    if "--first" in sys.argv:
        try:
            idx = sys.argv.index("--first")
            first_n = int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            pass

    if is_cron:
        user_input = 'a'
        print(f"{GREEN}Running in non-interactive/cron mode. Auditing all integrations headlessly...{RESET}")
    elif first_n is not None:
        user_input = 'first'
        print(f"{GREEN}Auditing first {first_n} integrations headlessly...{RESET}")
    else:
        # Show numbered menu
        print(f"{BLUE}Parsed Integrations Menu:{RESET}")
        for idx, item in enumerate(integrations, 1):
            title = item.get("title", "Unknown API")
            print(f"  [{idx}] {YELLOW}{title}{RESET}")
        print(f"  [A] {GREEN}Audit ALL integrations{RESET}")
        print("  [Q] Exit")

        try:
            user_input = input(
                f"\nSelect an option to audit (1-{len(integrations)}, A, or Q): ").strip().lower()
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Exiting auditor. Goodbye!{RESET}")
            sys.exit(0)

    if user_input == 'q':
        print(f"{YELLOW}Exiting auditor. Goodbye!{RESET}")
        sys.exit(0)

    targets = []
    if user_input == 'a':
        targets = integrations
        print(
            f"\n{GREEN}Starting full audit of all {len(integrations)} integrations...{RESET}")
    elif user_input == 'first':
        targets = integrations[:first_n]
        print(f"\n{GREEN}Starting audit of first {first_n} integrations...{RESET}")
    else:
        try:
            val = int(user_input)
            if 1 <= val <= len(integrations):
                targets = [integrations[val - 1]]
                title = targets[0].get("title", "Unknown API")
                print(
                    f"\n{GREEN}Starting single audit for: {YELLOW}{title}{RESET}")
            else:
                print(f"{RED}Invalid selection. Exiting.{RESET}")
                sys.exit(1)
        except ValueError:
            print(f"{RED}Invalid input. Exiting.{RESET}")
            sys.exit(1)

    OUTPUT_FILE = "output.txt"

    cache = load_cache()
    final_output = []

    print(f"\n{GREEN}[2/3] Auditing selection via Gemini...{RESET}")
    cache_modified = False

    for idx, item in enumerate(integrations, 1):
        title = item.get("title", "Unknown API")
        

        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', title.lower())
        current_hash = get_item_hash(item)

        if item not in targets:
            entry = cache.get(clean_name)
            if entry and entry.get("last_full_report"):
                print(
                    f"[{idx}/{len(integrations)}] Loading previous report for {YELLOW}{title}{RESET} from cache...")
                output_item = item.copy()
                output_item["audit_report"] = "NO_CHANGE"
                final_output.append(output_item)
            else:
                print(
                    f"[{idx}/{len(integrations)}] Skipping {YELLOW}{title}{RESET} (Not audited yet).")
            continue

        entry = cache.get(clean_name)
        previous_report = entry.get("last_full_report") if entry else None

        if entry and current_hash == entry.get(
                "input_hash") and not force_scan:
            print(f"[{idx}/{len(integrations)}] Auditing {YELLOW}{title}{RESET}...")
            print(f"\n{BLUE}--- AUDIT RESULTS FOR {title} ---{RESET}")
            print(
                f"{GREEN}No changes detected since the last scan (Cache hit)!{RESET}")
            print(f"{BLUE}---------------------------------------{RESET}\n")

            output_item = item.copy()
            output_item["audit_report"] = "NO_CHANGE"

            notify_email = item.get("notify_email") or item.get("notifyEmail")
            if notify_email:
                html_report = generate_html_report([output_item])
                send_report_via_email(
                    notify_email,
                    html_report,
                    f"API Audit Report: {title}",
                    is_html=True)

            final_output.append(output_item)
            continue

        print(f"[{idx}/{len(integrations)}] Auditing {YELLOW}{title}{RESET}...")
        
        audit_res = query_gemini_search(api_key, item, previous_report)

        is_no_change = False
        if previous_report and "NO_CHANGE_DETECTED" in audit_res:
            is_no_change = True
        elif previous_report:
            import difflib
            similarity = difflib.SequenceMatcher(
                None, previous_report, audit_res.strip()).ratio()
            if similarity > 0.85:
                is_no_change = True

        output_item = item.copy()

        if is_no_change:
            print(f"\n{BLUE}--- AUDIT RESULTS FOR {title} ---{RESET}")
            print(f"{GREEN}No changes detected since the last scan!{RESET}")
            print(f"{BLUE}---------------------------------------{RESET}\n")

            output_item["audit_report"] = "NO_CHANGE"

            cache[clean_name] = {
                "input_hash": current_hash,
                "last_scanned": datetime.now().isoformat(),
                "last_full_report": previous_report
            }
        else:
            print(f"\n{BLUE}--- AUDIT RESULTS FOR {title} ---{RESET}")
            print(f"{GREEN}New Report Generated.{RESET}")
            print(f"{BLUE}---------------------------------------{RESET}\n")

            try:
                output_item["audit_report"] = json.loads(audit_res)
            except json.JSONDecodeError:
                # Try aggressive cleanup or regex parsing to maintain
                # structured output
                try:
                    fixed_res = re.sub(r'\}\s*\}$', ']\n}', audit_res.strip())
                    output_item["audit_report"] = json.loads(fixed_res)
                except Exception:
                    output_item["audit_report"] = parse_malformed_json_to_dict(
                        audit_res)
            except Exception:
                output_item["audit_report"] = parse_malformed_json_to_dict(
                    audit_res)

            cache[clean_name] = {
                "input_hash": current_hash,
                "last_scanned": datetime.now().isoformat(),
                "last_full_report": audit_res.strip()
            }

        notify_email = item.get("notify_email") or item.get("notifyEmail")
        if notify_email:
            html_report = generate_html_report([output_item])
            attachment_name = f"{clean_name}_audit_report.pdf"
            pdf_bytes = generate_pdf_report([output_item], attachment_name)
            send_report_via_email(
                notify_email,
                html_report,
                f"API Audit Report: {title}",
                is_html=True,
                attachments=[
                    (attachment_name,
                     pdf_bytes)])

        final_output.append(output_item)
        cache_modified = True

    if cache_modified:
        save_cache(cache)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(generate_text_report(final_output))
    print(f"\n{GREEN} Success! API Audit file generated successfully at:{RESET}")
    print(f"{BLUE}{os.path.abspath(OUTPUT_FILE)}{RESET}\n")

    if email_recipient:
        html_report = generate_html_report(final_output)
        pdf_bytes = generate_pdf_report(
            final_output, "combined_audit_report.pdf")
        send_report_via_email(
            email_recipient,
            html_report,
            "Complete API Diagnostic Audit Report",
            is_html=True,
            attachments=[
                ("combined_audit_report.pdf",
                 pdf_bytes)])


if __name__ == "__main__":
    main()
