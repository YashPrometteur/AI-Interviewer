"""Phase 1: Shared utilities for resume file parsing, text sanitization, and token limit truncation."""
import io
import logging
from typing import Tuple
from fastapi import HTTPException

logger = logging.getLogger("ai_interviewer")

def sanitize_and_truncate_text(text: str, max_chars: int = 15000, context_label: str = "Text") -> str:
    """Sanitizes text and truncates safely with explicit logging if it exceeds character limits."""
    cleaned = (text or "").strip()
    if len(cleaned) > max_chars:
        logger.warning(
            f"⚠️ {context_label} exceeded maximum safe length ({len(cleaned)} chars). "
            f"Truncating to {max_chars} chars to protect LLM context windows."
        )
        return cleaned[:max_chars]
    return cleaned

def extract_text_from_file_bytes(content: bytes, filename: str) -> str:
    """Extracts raw plain text from PDF, DOCX, or plain text bytes without crashing."""
    lower_name = filename.lower()
    extracted_text = ""

    # PDF Parsing
    if lower_name.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages_text = []
            for page_idx, page in enumerate(reader.pages):
                txt = page.extract_text()
                if txt:
                    pages_text.append(txt)
            extracted_text = "\n".join(pages_text)
        except Exception as e:
            logger.warning(f"pypdf extraction failed for {filename}: {e}. Falling back to basic decode.")
            extracted_text = content.decode("utf-8", errors="ignore")

    # DOCX Parsing
    elif lower_name.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            extracted_text = "\n".join([p.text for p in doc.paragraphs if p.text])
        except Exception as e:
            logger.warning(f"docx extraction failed for {filename}: {e}. Falling back to raw decode.")
            extracted_text = content.decode("utf-8", errors="ignore")

    # TXT or generic text fallback
    else:
        try:
            extracted_text = content.decode("utf-8")
        except UnicodeDecodeError:
            extracted_text = content.decode("latin-1", errors="ignore")

    return extracted_text.strip()
