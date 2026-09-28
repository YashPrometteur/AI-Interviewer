"""Phase 3: FastAPI route handlers for candidate proctoring and integrity telemetry."""
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from pymongo.database import Database

from app.db.database import get_db
from app.db.schemas import ProctoringEventCreate, ProctoringEventOut, ProctoringFrameResponse
from app.proctoring import service

router = APIRouter()


@router.post("/sessions/{session_id}/proctoring-event", response_model=ProctoringEventOut, status_code=status.HTTP_200_OK)
def log_proctoring_event_endpoint(
    session_id: str,
    payload: ProctoringEventCreate,
    db: Database = Depends(get_db)
):
    """Ingests browser-native proctoring events (tab switches, window focus loss, multi-screen detection)."""
    return service.log_proctoring_event(
        db=db,
        session_id=session_id,
        event_type=payload.event_type,
        question_id=payload.question_id,
        details=payload.details,
        screenshot_base64=payload.screenshot_base64
    )


@router.post("/sessions/{session_id}/proctoring-frame", response_model=ProctoringFrameResponse, status_code=status.HTTP_200_OK)
async def analyze_proctoring_frame_endpoint(
    session_id: str,
    frame_file: UploadFile = File(..., description="JPEG/PNG snapshot from candidate camera"),
    question_id: Optional[str] = Form(None, description="Active question ID during sampling"),
    db: Database = Depends(get_db)
):
    """Analyzes a periodic video frame snapshot for person count and face visibility without interrupting session flow."""
    frame_bytes = await frame_file.read()
    return service.process_proctoring_frame(
        db=db,
        session_id=session_id,
        frame_bytes=frame_bytes,
        question_id=question_id
    )
