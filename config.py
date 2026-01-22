prompt = """
You are given a list of invoice texts. Each entry is the full text from one invoice. Your task is to extract structured data from each invoice and return a JSON list of dictionaries.

Each invoice should be converted into one or more dictionaries with these keys:

- invoice_number (If "Invoice Number" is not found, you may use alternative terms such as "Challan Number", "Bill Number", "Invoice #", "Invoice No", "Do No", etc. Treat these as invoice_no.)
- invoice_date (formatted as "MMM DD YYYY", e.g., "Dec 20 2012")
- gst_number (if present, else empty string)
- vendor_name (if found, else empty)
- total_amount (the grand total including all taxes, shipping, etc.)
- description (a short 2–3 word category describing the purpose of the invoice, inferred from product/item names)
- raw_text 

🧠 INVOICE DESCRIPTION RULES:
- Use the product name or description name or item name to guess the purpose of the invoice.
- Examples:
    - Items like bread, snacks, beverages → "Groceries"
    - Office supplies → "Office Supplies"
    - Hardware tools → "Hardware & Electrical"
    - Beauty/skin/hair products → "Personal Care"
    - Clothing/fashion → "Fashion/Retail"
    - Food, restaurant meals → "Food & Dining"
    - Tech, phones, laptops → "Electronics"
- If you're unsure, use a general category like "General Retail"
- Keep it short (2–3 words max)

📌 IMPORTANT RULES:
- DO NOT skip any invoices. Extract data from all invoices provided, even if fields are partially missing.
- If a field is missing or not found, return an empty string "".
- Support any currency: USD ($), INR (₹), EUR (€), MYR (RM), etc.
- 🏗️ HANDLING COMPLEX & MULTI-LINE LAYOUTS:
    - Identifying Totals: Look for "Grand Total", "Total Fare", "Total Invoice Value", "Amount Payable", or "Balance Due".
    - Identifying Dates: Look for "Invoice Date", "Date of Journey", "Boarding Date", or "Dated".
    - If labels and values are separated by distance or fragmented across lines, perform a thorough search to connect them. Always choose the highest numerical value as the total_amount if multiple subtotals are present.
- Return all invoice data — do not filter or ignore based on total amount or missing fields.
- Always return a list of dictionaries — one dictionary per invoice.

Now extract structured data from the following invoice texts:
"""