# Invoice AI - MVP

This repository contains a live Minimum Viable Product (MVP) implementation of Invoice AI.
The system demonstrates an end-to-end workflow for invoice processing: from file ingestion and OCR extraction to AI-based classification, fraud detection, VAT logic, chatbot integration, and a fully interactive dashboard.
The MVP is designed for public testing and runs on free-tier services.

----------------------------------------------------------------
SCOPE COVERAGE

1. Authentication
- Google & Facebook login via Firebase Auth
- User profiles stored securely
- Session history and login tracking

2. Invoice Upload
- Upload PDF or image files directly via browser
- Automatic backend processing triggered on upload

3. AI Automation Workflow
- OCR extraction (Tesseract / Google Vision ready)
- Field parsing: vendor, date, amount, currency, tax ID
- Language detection (mock / langdetect)
- Invoice classification: service / product / recurring
- Fraud detection: Isolation Forest + statistical rules
- VAT & tax logic: EU VAT rules (extendable for ZATCA / UAE FTA)
- Structured data stored in Firebase Firestore

4. Chatbot Agent
- Integrated chatbot powered by OpenRouter (GPT-4o-mini)
- Queries local data (invoices, fraud scores, totals)
- Supports natural language questions:
  - What invoices are risky this month?
  - Total spent in August
  - Export my tax summary
- Generates downloadable CSV tax reports

5. Dashboard
- KPI summary cards: invoice volume, risky invoices, total amount, VAT
- Monthly totals displayed as charts
- Top vendor analysis
- Interactive invoice table with OCR preview
- Export to CSV functionality
- Embedded chatbot panel

6. Admin Panel (Optional)
- Not included in MVP, but architecture supports adding user management and system monitoring

7. Hosting & Deployment
- Frontend: Next.js on Vercel (free tier)
- Backend: FastAPI on Render / Railway (free tier)
- Database & Auth: Firebase (Firestore + Auth)
----------------------------------------------------------------

API Documentation (Swagger UI)

The backend exposes a full **REST API** with interactive documentation via **Swagger UI**.
You can explore and test all endpoints (upload invoice, list invoices, chat, etc.) directly in your browser:
[Live Swagger UI] https://invoice-ai-mvp.onrender.com/docs
<img width="1920" height="952" alt="Ekran Resmi 2025-09-14 18 10 24" src="https://github.com/user-attachments/assets/e723953f-59a5-423b-83bb-90ee61d1acd3" />

----------------------------------------------------------------
TECH STACK

Frontend: Next.js 15, React 18, TailwindCSS
Backend: Python FastAPI
Database: Firebase Firestore
Auth: Firebase Authentication (Google, Facebook)
AI/ML: Tesseract OCR, scikit-learn (Isolation Forest), OpenRouter LLM
Deployment: Vercel (frontend), Render/Railway (backend)

----------------------------------------------------------------
REQUIREMENTS

- Node.js >= 18
- Python >= 3.10
- pip + virtualenv
- Git
- Firebase Service Account (JSON)
- OpenRouter API key (or OpenAI API key)

----------------------------------------------------------------
SETUP AND RUN

# Clone repository
git clone https://github.com/BekirBz/invoice-ai-mvp.git
cd invoice-ai-mvp

# FRONTEND setup
cd frontend
npm install
npm run dev   # runs at http://localhost:3000

# BACKEND setup
cd ../backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Environment variables (.env)
OPENROUTER_API_KEY=sk-or-XXXX
OPENROUTER_SITE=http://localhost:3000
OPENROUTER_TITLE="Invoice AI MVP"

# Start backend
uvicorn main:app --reload --port 8000

Frontend available at: http://localhost:3000
Backend available at: http://localhost:8000

----------------------------------------------------------------
<img width="1410" height="942" alt="Ekran Resmi 2025-09-14 15 21 29" src="https://github.com/user-attachments/assets/2c852bc8-e795-426d-825b-c6c3ae2d1ce1" />


Dashboard Overview
- KPIs (Invoices, Risky, Total, VAT)
- Monthly totals chart
- Top vendors list
- Invoice table

Chatbot
- Natural language queries about invoices
- Example: "Export my tax summary" → generates CSV download
<img width="1328" height="952" alt="Ekran Resmi 2025-09-14 16 01 13" src="https://github.com/user-attachments/assets/6465c12f-d98a-4d28-9b1f-a561e830966d" />

----------------------------------------------------------------
DELIVERABLES

- Publicly hosted working demo (frontend + backend)
- GitHub repo with code & documentation
- REST API (FastAPI + Swagger UI)
- Sample credentials (Firebase Auth demo)
- README with full setup instructions

----------------------------------------------------------------
EVALUATION HIGHLIGHTS

- End-to-end functional AI workflow
- Usable chatbot with LLM integration
- Clean, responsive Next.js UI
- Secure, modular backend design
- Free-tier deployment ready
- Bonus: CSV tax report export, dashboard charts, user session tracking
