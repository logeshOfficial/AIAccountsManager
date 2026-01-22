import fitz  # PyMuPDF
from app_logger import get_logger

logger = get_logger(__name__)

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts all text from a PDF document provided as bytes."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text.strip()
    except Exception as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        return ""
