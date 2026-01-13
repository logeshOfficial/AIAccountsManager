# 🧾 Invoice Intelligence Automation

This project automates invoice data extraction from scanned documents (PDFs, images), organizes the data into structured Excel files by month and year, and enables natural language querying using Google's Gemini LLM (Generative AI).

---

## 📂 Project Structure

📦 project-root
├── test/ # Input directory containing raw invoice PDFs/images
├── scanned_docs/ # Successfully processed invoices
├── invalid_docs/ # Invoices with missing/invalid data
├── output/ # Generated Excel reports
├── .env # Contains API keys
├── requirements.txt # Python dependencies
├── invoice_processor.py # Main invoice processing script
└── query_tool.py # Query invoice data using natural language


---

## ✅ Features Implemented

- ✅ OCR extraction using EasyOCR and PyMuPDF
- ✅ Gemini-based invoice data extraction
- ✅ Categorizes invoices by purpose
- ✅ Saves data into structured Excel files
- ✅ Supports natural language queries for filtering and summaries
- ✅ Handles multiple formats (.pdf, .jpg, .png, etc.)

---

## 🛠️ Installation  

1. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate   # On macOS/Linux
venv\Scripts\activate      # On Windows

pip install -r requirements.txt

# -----------------------------------------
⚙️ Environment Setup 

Create a .env file in the project root with your Gemini API key:

You can get the key from: https://aistudio.google.com/app/apikey.

GOOGLE_API_KEY=your_gemini_api_key_into_envfile

🚀 Usage
Step 1: Extract Invoices

python invoice_processor.py

- Reads documents from ./test/

- Extracts data using OCR + Gemini

- Moves valid docs to scanned_docs/, invalid to invalid_docs/

- Writes structured Excel files into ./output/

Step 2: Ask Questions

python query_tool.py

- Type queries like:

- "Show total spent on Groceries in Feb 2023"

- "How many invoices in 2022?"

- "List invoices from July 2024"

- Type e to exit.