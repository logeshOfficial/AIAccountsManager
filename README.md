# 📊 AI Accounts Manager v2.0: Agentic Financial Intelligence

An elite, **multi-agent financial ecosystem** that automates the entire lifecycle of corporate expense management. From intelligent OCR extraction to deep trend analysis and automated report delivery, powered by **LangGraph** and **SOTA LLMs**.

---

## 🚀 Core Intelligence Pillars

### 🤖 Multi-Agent Framework (LangGraph)
The system leverages a sophisticated DAG-based workflow to resolve complex financial queries:
- **🧠 Analyst Agent**: Conducts granular data investigation, resolves conversational references, and provides deep natural language summaries of financial health.
- **🎨 Designer Agent**: Intelligently selects the optimal visualization (Pie, Bar, Line, or "Sensex" Trends) based on data density and timeframe context.
- **💼 Secretary Agent**: Orchestrates professional Excel generation and secure email delivery to stakeholders.

### 📄 High-Efficiency PDF Extraction
The system focuses on high-precision text extraction from PDF documents, ensuring rapid and accurate processing of digital financial records.

### 📈 Smart Year & Month Reports
Intelligent Excel generation logic:
- **Yearly Reports**: Generates a single workbook with **separate sheets for each month** (Jan-Dec) automatically.
- **Granular Filtering**: Focus on specific months, dates, or vendors with single-sheet extracts.
- **Automated Delivery**: Email reports directly to custom destinations (e.g., "Email the 2025 report to finance").
- **Vendor Insights**: Prioritizes grouping by **Vendor Name** when keywords like "consumed" or "most" are detected.
- **Premium Themes**: Uses calibrated "Plotly White" templates with diamond-open markers for professional "Sensex-style" growth analysis.

---

## 🛠️ Technical Architecture

### Stack
- **Backend**: Python 3.10+
- **Agentic Logic**: LangGraph / LangChain
- **UI Framework**: Streamlit (Modernized Layout)
- **Database**: Supabase (PostgreSQL)
- **Models**: Groq (Llama-3.3-70b), OpenAI (GPT-4o-mini), Google (Gemini)
- **Exports**: OpenPyXL & Plotly HTML

### Storage & Privacy
- **Automatic Cleanup**: Temporary reports and charts are automatically purged from the `exports/` directory immediately after delivery or after 20 minutes of inactivity.
- **Session Isolation**: Multi-tenant architecture ensures users only see their own financial data.

---

## 📂 Installation & Setup

### 1. Environment Configuration
Populate `.streamlit/secrets.toml` or your environment variables:
```toml
# AI Keys
groq_api_key = "..."
openai_api_key = "..."
gemini_api_key = "..."

# Database & Auth
supabase_url = "..."
supabase_key = "..."
GOOGLE_CLIENT_ID = "..."
GOOGLE_CLIENT_SECRET = "..."

# Services
smtp_user = "finance@company.com"
smtp_password = "app-password"
```

### 2. Launch
```powershell
python -m venv venv
.\venv\Scripts\activate.ps1
pip install -r requirements.txt
streamlit run main.py
```

---

## 🛡️ Role-Based Access
- **Finance Admins**: Access to global logging and full database visibility.
- **System Users**: Isolated workspace for personal invoice management.

*Copyright © 2026 AI Accounts Manager. All rights reserved.*