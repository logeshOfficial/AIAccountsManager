# 📊 AI Accounts Manager: Agentic Invoice Intelligence

An elite, **multi-agent financial assistant** that automates the entire lifecycle of invoice management—from intelligent extraction to deep analysis and automated delivery.

---

## 🚀 Key Features

### 🤖 Multi-Agent Framework (LangGraph)
Powered by a sophisticated agentic workflow:
- **Analyst Node**: Performs deep data lookup, extracts granular filters (vendor, year, month, date), and provides natural language explanations.
- **Designer Node**: Intelligently selects and generates data visualizations (Plotly) based on your query context.
- **Secretary Node**: Handles high-fidelity Excel report generation and automated email delivery.

### 📄 3-Tier Advanced Vision Engine
Robust OCR hierarchy ensuring maximum extraction accuracy:
1. **Tier 1 (Gemini 2.0)**: SOTA multimodal extraction.
2. **Tier 2 (GPT-4o)**: High-precision fallback.
3. **Tier 3 (Local Donut)**: On-device OCR fallback (naver-clova-ix/donut-base) using `transformers`.

### 📈 Smart Year & Month Reports
Intelligent Excel generation logic:
- **Yearly Reports**: Generates a single workbook with **separate sheets for each month** (Jan-Dec) automatically.
- **Granular Filtering**: Focus on specific months, dates, or vendors with single-sheet extracts.
- **Automated Delivery**: Email reports directly to custom destinations (e.g., "Email the 2025 report to finance@company.com").

---

## 🛠️ Setup Guide

### 1. Installation
```powershell
git clone <repository-url>
cd AIAccountsManager
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration (`.streamlit/secrets.toml`)
Populate your secrets with these keys:

| Key | Description |
| :--- | :--- |
| **LLMs** | `groq_api_key`, `openai_api_key`, `gemini_api_key` |
| **Database** | `supabase_url`, `supabase_key` |
| **GCP** | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `REDIRECT_URI` |
| **Email** | `smtp_user` (Gmail), `smtp_password` (App Password) |
| **Config** | `admin_email`, `INPUT_DOCS` (Drive folder name) |

### 3. Running the App
```powershell
# From the root directory
streamlit run main.py
```

---

## 📖 Pro Workflow

### 1. Sync & Process
Navigate to **Drive Manager** to sync PDFs from Google Drive. The system extracts data and moves processed files to `scanned_docs`.

### 2. Agentic Chat
Go to **Chat_Bot** and interact with the agents:
- *"Tell me about the Amazon invoice from last week."*
- *"Graph my Microsoft expenses for 2024."*
- *"Generate an Excel for all 2025 invoices and email it to me."*

### 3. Multi-Sheet Exports
Ask for a **Year** (e.g., "for 2025") to receive a consolidated Excel with sheets named by month. Ask for a **Month** for a focused single-sheet extract.

---

## 📂 Project Architecture

- `main.py`: Entry point and Streamlit routing.
- `agent_manager.py`: LangGraph multi-agent logic and state definition.
- `vision_engine.py`: 3-tier OCR hierarchy logic.
- `db.py`: Supabase PostgreSQL integration.
- `invoice_processor.py`: Field extraction and normalization.
- `chat_bot.py`: Direct interface for agent interaction.

---

## 🛡️ Security & Roles
- **Admins**: Full global visibility and system log access.
- **Users**: Strict tenant-based isolation (only see your own invoices).