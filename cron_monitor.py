import urllib.request
import json
import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def send_summary_email(recipient_email, results):
    # Using the same SMTP credentials from audit_apis.py
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        print("SMTP_USER and SMTP_PASS environment variables not set in .env. Cannot send email.")
        return

    # Categorize results
    total = len(results)
    errors = [r for r in results if r['status'] == 'error']
    warns = [r for r in results if r['status'] == 'warn']
    oks = [r for r in results if r['status'] == 'ok']

    # Build HTML Email
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .container {{ border: 1px solid #ccc; padding: 20px; border-radius: 10px; }}
            .error {{ color: red; font-weight: bold; }}
            .warn {{ color: orange; font-weight: bold; }}
            .ok {{ color: green; font-weight: bold; }}
            ul {{ list-style-type: none; padding-left: 0; }}
            li {{ padding: 10px; border-bottom: 1px solid #eee; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>API Monitor Cron Summary</h2>
            <p><strong>Total APIs Scanned:</strong> {total}</p>
            <p><span class="ok">Healthy (OK):</span> {len(oks)}</p>
            <p><span class="warn">Warnings:</span> {len(warns)}</p>
            <p><span class="error">Errors (Down):</span> {len(errors)}</p>
            
            <hr>
            <h3>Failing or Warning APIs:</h3>
    """
    
    if not errors and not warns:
        html += "<p>All APIs are currently Healthy! No action required.</p>"
    else:
        html += "<ul>"
        for api in errors + warns:
            color_class = "error" if api['status'] == 'error' else "warn"
            html += f"""
                <li>
                    <span class="{color_class}">[{api['status'].upper()}]</span> <b>{api['service']}</b><br>
                    HTTP Code: {api['http_code']} | Latency: {api['latency_ms']}ms<br>
                    Note: <i>{api['note']}</i>
                </li>
            """
        html += "</ul><p><b>Next Steps:</b> Go to your API Dashboard and run the Deep AI Diagnostics to fix these issues.</p>"
        
    html += """
        </div>
    </body>
    </html>
    """
    
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient_email
        msg['Subject'] = f"API Scan Summary: {len(errors)} Errors, {len(warns)} Warnings"
        msg.attach(MIMEText(html, 'html'))
        
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        print(f"Successfully sent summary email to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cron_monitor.py <your_email@example.com>")
        sys.exit(1)
        
    email = sys.argv[1]
    
    print("Triggering background scan via /api/check/all ...")
    # This hits the local backend server endpoint that triggers a scan for all active APIs
    req = urllib.request.Request("http://localhost:5000/api/check/all", method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            results = res_data.get('results', [])
            print(f"Successfully scanned {len(results)} APIs.")
            
            # Send the beautiful HTML summary email
            send_summary_email(email, results)
    except Exception as e:
        print(f"Error calling API monitor: {e}")
