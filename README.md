# API Monitor & Diagnostic Auditor

A full-stack, autonomous API monitoring dashboard and diagnostic auditor. This application allows you to track the health of various API endpoints (latency, HTTP status) and use the **Gemini 2.5 Flash AI model** to generate in-depth, professional PDF audit reports for any failing or outdated integrations.

## 🚀 Quick Start

The fastest way to get everything up and running is to use the included startup script.

1. **Configure Environment Variables**  
   Create or edit the `.env` file in the root directory to include your credentials:
   ```env
   GEMINI_API_KEY="YOUR_GEMINI_KEY"
   SMTP_USER="your-email@example.com"
   SMTP_PASS="your-app-password"
   ```

2. **Run the Startup Script**  
   Run the `start_webapp.sh` script to automatically install dependencies and start both the backend and frontend servers:
   ```bash
   bash start_webapp.sh
   ```

3. **Access the Application**  
   - **Frontend Dashboard:** [http://localhost:5173](http://localhost:5173)
   - **Backend API:** [http://localhost:5000](http://localhost:5000)

---

## 📂 Project Structure

- **`/backend`**: Contains the Flask API (`app.py`), the AI auditor logic (`audit_apis.py`), and the SQLite database configuration.
- **`/frontend`**: Contains the React + Vite frontend dashboard.
- **`.env`**: Stores sensitive configurations (API keys, SMTP details).
- **`start_webapp.sh`**: The one-click startup script.

---

## 🛠️ Manual Setup

If you prefer to run the components separately:

### Backend Setup
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the Flask backend server:
   ```bash
   python3 backend/app.py
   ```

### Frontend Setup
1. Navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```

---

## 📖 Usage Guide

Once the application is running, follow these steps to manage and monitor your APIs:

### 1. Adding an API to Monitor
- Open the **Frontend Dashboard** (default: `http://localhost:5173`).
- On the left panel, use the **Add a Service** form to manually enter the API name, endpoint URL, description, and notification email.
- Alternatively, use the **Quick-Add Popular APIs** dropdown to instantly monitor common services (like Stripe, Twilio, etc.).

### 2. Bulk AI Scanning & Network Checks
- Click the **Scan All APIs** button in the top navigation bar to trigger a bulk deep audit for all registered APIs.
- The system will process each API in the background using Gemini, and instantly email the generated professional PDF reports to their respective notification emails without blocking your workflow.
- Basic network pings (latency and HTTP status checks) are handled entirely automatically by the background scheduler.

### 3. Automated Scanning & Notifications
- Click **Schedule** in the top navigation to configure automatic background scans.
- Set an interval (Minutes, Hours, or Days) and enter a global notification email. The system will automatically check the APIs and send email alerts if any issues are detected.

### 4. AI Diagnostics & Deep Auditing
- In the bottom **AI Diagnostics & Deep Auditing** panel, select one of your registered API services.
- If an endpoint is failing, you can use **Diagnose Issue** or **Suggest Fixes** for instant Gemini-powered troubleshooting.
- Click **Compile PDF Report** to generate a comprehensive audit document for just that API. The professional report is displayed as an embedded PDF and automatically saved to the backend `/reports` directory.

---

## ✨ Key Features

- **Automated Health Checks:** Monitor latency and HTTP status codes for all your third-party integrations.
- **Centralized Dashboard:** Easily add, edit, and track API endpoints from a clean React-based interface.
- **Gemini-Powered Diagnostics:** Leverage Gemini 2.5 Flash to automatically diagnose connection issues and suggest fixes.
- **Professional PDF Reports:** Generate detailed, stylized PDF audits highlighting versioning, deprecations, and security risks.
- **Differential Caching:** Scans are automatically cached to save AI credits. If there are no changes, the backend loads the previous report.
- **Email Notifications:** Optionally send HTML reports with PDF attachments directly to a developer's inbox.
