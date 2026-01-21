# 📊 AI Accounts Manager

This project is an **AI-powered financial assistant** that automates invoice processing and provides a natural language interface for querying your financial data. It uses Google's Gemini, Groq, and Hugging Face models to extract data from documents and answer user questions.

---

## ✅ Key Features

- **📄 Automated Invoice Processing**: Extracts data from PDFs, Images, and CSVs on Google Drive using specific parsing logic.
- **🤖 AI Chatbot**: Ask questions like "How much did I spend on groceries in 2024?" or "Show me invoice #123".
- **🧠 Multi-Model Intelligence**: 
    - **Primary**: Hugging Face / OpenAI (Llama 3)
    - **Fallback**: Groq (Llama 3 fast inference)
    - **Fallback**: Google Gemini (Flash 1.5)
- **👥 Role-Based Access**: 
    - **Admins**: View all invoices and access system logs.
    - **Users**: View only their own data.
- **📁 Google Drive Integration**: Seamlessly syncs with your Drive to process and organize documents.
- **📜 Admin Logging**: Built-in log viewer to monitor system health and errors.

---

## 🚀 Setup Guide

### 1. Prerequisites
- Python 3.9+
- A Google Cloud Project with Drive API enabled.
- API Keys for: OpenAI/HuggingFace, Groq, Google Gemini.

### 2. Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd AIAccountsManager
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # Mac/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Configuration (`secrets.toml`)

Streamlit uses `secrets.toml` for sensitive config. Create a file at `.streamlit/secrets.toml` with the following:

```toml
# AI Model Keys
openai_api_key = "your_primary_key"
groq_api_key = "your_groq_key"
gemini_api_key = "your_gemini_key"

# Models (Optional overrides)
openai_model = "meta-llama/Meta-Llama-3-8B-Instruct"
groq_model = "llama3-8b-8192"
gemini_model = "gemini-1.5-flash"

# Admin Config
admin_email = "your-email@gmail.com"  # The admin's Google email

# Drive Configuration
INPUT_DOCS = "Invoices_Input" # Name of folder in Drive to watch
```

*Note: You will also need a `client_secret.json` in the root directory for Google OAuth.*

---

## 📖 New User Workflow

### Step 1: Login
- Open the app. You will be prompted to **Login with Google**.
- This ensures your data is secure and linked to your account.

### Step 2: Process Invoices
1.  Navigate to **"Drive_Manager"** in the sidebar.
2.  Click **"Start Invoice Processing"**.
3.  The system will scan the folder specified in `INPUT_DOCS` on your Google Drive.
4.  It will extract details (Date, Vendor, Amount, etc.) and save them to the database.
5.  Processed files are moved to `scanned_docs/` or `invalid_docs/` in your Drive.

### Step 3: Chat with Your Data
1.  Navigate to **"Chat_Bot"** in the sidebar.
2.  Type a question:
    - *"Show me all invoices from January 2024"*
    - *"What is the total spent on Office Supplies?"*
    - *"Find invoice #INV-2023-001"*
3.  The AI will analyze the database and provide a summarized answer along with the source data.

### Step 4: Admin Tools (Admins Only)
- If you are logged in with the `admin_email`, you will see a **"Show Logs"** checkbox in the sidebar.
- Use this to view system logs (`app.log`) for debugging errors without needing server access.

---

## 📂 Project Structure

```
AIAccountsManager/
├── main.py                 # App Entry Point & Routing
├── chat_bot.py             # Chat Interface Logic
├── managers/
│   ├── llm_manager.py      # AI Model Handling (Primary -> Groq -> Gemini)
│   ├── invoice_manager.py  # Data Logic (Filters, Calculations)
├── utils/
│   ├── app_logger.py       # Centralized Logging
│   ├── admin_utils.py      # Admin Components (Log Viewer)
├── drive_manager.py        # Google Drive API Interactions
├── invoice_processor.py    # Invoice Parsing Engine
├── db.py                   # Database Operations (SQLite)
└── oauth.py                # Google Authentication
```

---

## 🛠️ Troubleshooting

- **Google Login Fails**: Ensure your `redirect_uri` matches your Streamlit deployment URL in the Google Cloud Console.
- **Model Errors**: Check `secrets.toml` keys. If Primary fails, the system auto-retries with Groq, then Gemini. Use the "Show Logs" feature to see which one failed.