# API Auditor Web Application

This directory contains the completely isolated, full-stack implementation of the Autonomous API Diagnostic Auditor.

## Project Structure
- `/` (Root directory of Web App): Contains the Flask backend (`app.py`, `audit_apis.py` logic, `.env` file, and `requirements.txt`).
- `/frontend`: Contains the React + Vite frontend application.

---

## Getting Started

### 1. Prerequisites
Make sure you have `python3`, `pip`, and `node` (with `npm`) installed on your system.

### 2. Configure Environment Variables
The `webapp/.env` file has been prepopulated with your API keys. If you need to update them, modify `webapp/.env`:
```env
GEMINI_API_KEY="YOUR_KEY"
SMTP_USER="user"
SMTP_PASS="pass"
```

### 3. Backend Setup
Navigate to this directory (`webapp/`) and install Python dependencies:
```bash
pip install -r requirements.txt
```
Start the Flask backend server:
```bash
python3 app.py
```
The backend server will run on `http://localhost:5000`.

### 4. Frontend Setup
Navigate to the `frontend/` directory:
```bash
cd frontend
```
Install npm dependencies:
```bash
npm install
```
Start the Vite development server:
```bash
npm run dev
```
The React frontend will be available at `http://localhost:5173`.

---

## Features
- **Centralized Form:** Input API details (title, docs URL, and description) directly from the browser.
- **Model Selector:** Auditing powered by Gemini 2.5 Flash.
- **Differential Caching:** Scans are automatically cached and compared. If there are no changes, the backend loads the previous report.
- **In-Browser PDF Viewer:** Instantly view the styled, generated ReportLab PDF once the audit completes.
- **Email Notifications:** Optionally send the HTML report with the PDF attachment to a specified developer email.
