from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pymongo.database import Database

from app.db.database import get_db
from app.db.schemas import FullReportResponse
from app.reports import service

router = APIRouter()

@router.get("/reports/{session_id}", response_model=FullReportResponse)
def get_report_endpoint(session_id: str, db: Database = Depends(get_db)):
    """Fetches the complete interview evaluation report, scorecard, and full transcript for a session."""
    return service.get_full_report(db, session_id)

@router.get("/reports/{session_id}/export", response_class=HTMLResponse)
def export_report_html_endpoint(session_id: str, db: Database = Depends(get_db)):
    """Exports a standalone printable scorecard for the candidate evaluation."""
    html_content = service.generate_printable_html_report(db, session_id)
    return HTMLResponse(content=html_content, status_code=200)

