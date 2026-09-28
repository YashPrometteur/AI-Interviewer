"""Phase 1: Resume document text extraction and Job Description skill profiling parser."""
import logging
from typing import List, Dict, Any
from app.core.utils import extract_text_from_file_bytes, sanitize_and_truncate_text
from app.ai.chains import extract_skills_chain, extract_background_chain

logger = logging.getLogger("ai_interviewer")

def parse_resume(file_content: bytes, filename: str) -> str:
    """Parses raw text from uploaded resume bytes (supporting PDF, DOCX, TXT) and applies sanitization."""
    raw_text = extract_text_from_file_bytes(file_content, filename)
    cleaned_text = sanitize_and_truncate_text(raw_text, max_chars=15000, context_label=f"Resume ({filename})")
    return cleaned_text

def extract_skills_from_jd(jd_text: str) -> Dict[str, Any]:
    """Invokes AI chain to extract key skills and normalized importance weights from JD text."""
    sanitized_jd = sanitize_and_truncate_text(jd_text, max_chars=15000, context_label="Job Description")
    return extract_skills_chain(sanitized_jd)

def extract_candidate_background(resume_text: str, jd_skills: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Invokes AI chain to summarize candidate background against the extracted JD skills."""
    sanitized_resume = sanitize_and_truncate_text(resume_text, max_chars=15000, context_label="Candidate Resume")
    return extract_background_chain(sanitized_resume, jd_skills)
