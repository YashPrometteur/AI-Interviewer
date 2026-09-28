"""Phase 1: FastAPI route handlers for interview evaluation reports."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.schemas import FullReportResponse
from app.reports import service

router = APIRouter()

@router.get("/reports/{session_id}", response_model=FullReportResponse)
def get_report_endpoint(session_id: str, db: Session = Depends(get_db)):
    """Fetches the complete interview evaluation report, scorecard, and full transcript for a session."""
    return service.get_full_report(db, session_id)
