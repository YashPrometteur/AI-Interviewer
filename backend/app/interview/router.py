"""Phase 2: FastAPI route handlers for interview session management, audio/video capture, and candidate turn flow."""
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.responses import FileResponse
from pymongo.database import Database

from app.db.database import get_db
from app.db.schemas import (
    SessionCreateResponse, SessionListItem, NextQuestionResponse,
    QuestionOut, SessionQuestionsListResponse,
    AnswerSubmitRequest, AnswerEvaluationOut, CompleteSessionResponse
)
from app.interview import service
from app.interview import media
from app.interview import tts
from app.interview import avatar
from app.interview.audio_stream import router as audio_stream_router

router = APIRouter()
router.include_router(audio_stream_router)


@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_interview_session(
    candidate_name: str = Form(..., description="Full name of candidate"),
    candidate_email: str = Form(..., description="Email address of candidate"),
    jd_text: str = Form(..., description="Full text of Job Description"),
    resume_file: UploadFile = File(..., description="Candidate resume (PDF, DOCX, TXT)"),
    position: Optional[str] = Form("Software Engineer", description="Position/Role applied for"),
    interview_mode: str = Form("live", description="Interview mode: 'live' or 'async'"),
    answer_capture_type: str = Form("text", description="Answer capture type: 'text' or 'video'"),
    interviewer_photo: Optional[UploadFile] = File(None, description="Optional portrait photo for interviewer avatar"),
    interviewer_gender: Optional[str] = Form("auto", description="Interviewer voice gender: 'auto', 'male', or 'female'"),
    db: Database = Depends(get_db)
):
    """Creates a new interview session by parsing JD & resume, generating a question bank, and configuring mode."""
    resume_bytes = await resume_file.read()
    photo_bytes = await interviewer_photo.read() if interviewer_photo else None
    return service.start_session(
        db=db,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        jd_text=jd_text,
        resume_bytes=resume_bytes,
        resume_filename=resume_file.filename or "resume.pdf",
        position=position,
        interview_mode=interview_mode,
        answer_capture_type=answer_capture_type,
        interviewer_photo_bytes=photo_bytes,
        interviewer_photo_filename=interviewer_photo.filename if interviewer_photo else None,
        interviewer_gender=interviewer_gender
    )

@router.get("/sessions", response_model=List[SessionListItem])
def list_interview_sessions(db: Database = Depends(get_db)):
    """Retrieves all interview sessions for recruiter dashboard monitoring."""
    return service.list_sessions(db)

@router.get("/sessions/{session_id}/questions", response_model=SessionQuestionsListResponse)
def get_session_questions_endpoint(session_id: str, db: Database = Depends(get_db)):
    """Retrieves all generated questions for a session to allow candidate to maneuver through the question bank."""
    return service.get_session_questions(db, session_id)

@router.get("/sessions/{session_id}/questions/{question_id}", response_model=QuestionOut)
def get_session_question_by_id_endpoint(session_id: str, question_id: str, db: Database = Depends(get_db)):
    """Retrieves a specific question from the question bank by ID."""
    return service.get_session_question_by_id(db, session_id, question_id)

@router.get("/sessions/{session_id}/next-question", response_model=NextQuestionResponse)
def get_next_question_endpoint(session_id: str, exclude_id: Optional[str] = None, db: Database = Depends(get_db)):
    """Fetches the next question adaptively based on candidate's performance and validates session lifecycle."""
    return service.get_next_question(db, session_id, exclude_question_id=exclude_id)

@router.get("/sessions/{session_id}/questions/{question_id}/audio")
def get_question_audio_endpoint(session_id: str, question_id: str):
    """Streams pre-synthesized WAV audio for the specified interview question."""
    audio_path = tts.get_question_audio_path(session_id, question_id)
    if not audio_path or not audio_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found for this question.")
    return FileResponse(path=str(audio_path), media_type="audio/wav")

@router.get("/sessions/{session_id}/questions/{question_id}/avatar-video")
def get_question_avatar_video_endpoint(session_id: str, question_id: str):
    """Streams pre-rendered Wav2Lip MP4 lip-sync video for the specified bank question."""
    video_path = avatar.get_avatar_video_path(session_id, question_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar video not found for this question.")
    return FileResponse(path=str(video_path), media_type="video/mp4")

@router.get("/sessions/{session_id}/interviewer-photo")
def get_interviewer_photo_endpoint(session_id: str):
    """Streams uploaded interviewer portrait photo for session avatar / 2D animation."""
    photo_path = avatar.get_interviewer_photo_path(session_id)
    if not photo_path or not photo_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interviewer photo not found for this session.")
    return FileResponse(path=str(photo_path), media_type="image/jpeg")

@router.post("/sessions/{session_id}/answer", response_model=AnswerEvaluationOut)
def submit_answer_endpoint(session_id: str, payload: AnswerSubmitRequest, db: Database = Depends(get_db)):
    """Submits and evaluates candidate response to the current question (text-based)."""
    return service.submit_answer(
        db=db,
        session_id=session_id,
        question_id=payload.question_id,
        answer_text=payload.answer_text,
        answer_source="text"
    )

@router.post("/sessions/{session_id}/answer-recording", response_model=AnswerEvaluationOut)
async def submit_answer_recording_endpoint(
    session_id: str,
    question_id: str = Form(..., description="ID of the question being answered"),
    recording_file: UploadFile = File(..., description="Recorded audio/video file (webm, mp4, wav)"),
    db: Database = Depends(get_db)
):
    """Uploads recorded answer media, transcribes via local Whisper speech-to-text, and evaluates the transcribed answer."""
    file_bytes = await recording_file.read()
    if not file_bytes or len(file_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded recording file is empty or corrupted. Please record a complete answer."
        )

    # 1. Save media to local disk
    recording_path = media.upload_recording(
        session_id=session_id,
        question_id=question_id,
        file_bytes=file_bytes,
        filename=recording_file.filename or "answer.webm"
    )

    # 2. Lookup question's skill_tag and question_text to bias Whisper's initial_prompt and phonetic repair
    skill_tag = None
    question_text = None
    try:
        obj_id = service.parse_object_id(session_id)
        session_doc = db.sessions.find_one({"_id": obj_id})
        if session_doc:
            for q in session_doc.get("questions", []):
                if q.get("question_id") == question_id:
                    skill_tag = q.get("skill_tag")
                    question_text = q.get("text")
                    break
    except Exception:
        pass

    # 3. Transcribe recording using Whisper with technical vocabulary biasing and phonetic repair
    transcribed = media.transcribe_recording(recording_path, skill_tag=skill_tag, question_text=question_text)
    transcribed_text = (transcribed.get("text") or "").strip()
    if not transcribed_text or len(transcribed_text) < 2:
        transcribed_text = "[No audible response detected in recording]"

    # 4. Pass transcribed text into existing submit_answer pipeline
    return service.submit_answer(
        db=db,
        session_id=session_id,
        question_id=question_id,
        answer_text=transcribed_text,
        answer_source="video",
        recording_url=recording_path,
        transcription_confidence=transcribed.get("confidence"),
        transcription_mode=transcribed.get("transcription_mode", "real")
    )


@router.post("/sessions/{session_id}/transcribe-chunk")
async def transcribe_audio_chunk_endpoint(
    session_id: str,
    chunk_file: UploadFile = File(..., description="Short audio chunk for live transcript preview"),
    question_id: Optional[str] = Form(None)
):
    """Fast intermediate chunk transcription endpoint for live candidate speech preview."""
    file_bytes = await chunk_file.read()
    if not file_bytes or len(file_bytes) < 50:
        return {"text": "", "confidence": 0.0}

    # Save to temp chunk file
    temp_dir = Path(settings.RECORDINGS_DIR) / "chunks"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"chunk_{session_id}_{os.urandom(4).hex()}.webm"
    try:
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        transcribed = media.transcribe_recording(str(temp_path))
        return {
            "text": transcribed.get("text", "").strip(),
            "confidence": transcribed.get("confidence", 0.95),
            "mode": transcribed.get("transcription_mode", "real")
        }
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


@router.post("/sessions/{session_id}/complete", response_model=CompleteSessionResponse)
def complete_session_endpoint(session_id: str, db: Database = Depends(get_db)):

    """Finalizes the interview, computes overall weighted score, and generates the final evaluation report."""
    return service.complete_session(db, session_id)


@router.post("/sessions/{session_id}/session-video", status_code=status.HTTP_200_OK)
async def upload_session_video_endpoint(
    session_id: str,
    video_file: UploadFile = File(..., description="Full session master video file"),
    db: Database = Depends(get_db)
):
    """Uploads and associates the complete continuous interview video with the session document."""
    video_bytes = await video_file.read()
    video_url = service.save_session_video(db, session_id, video_bytes, video_file.filename)
    return {"session_id": session_id, "session_video_url": video_url}

