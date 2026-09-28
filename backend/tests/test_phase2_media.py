"""Automated Test Suite for Phase 2 Media & Session Lifecycles.
Tests:
- FFmpeg availability check
- Media upload and persistence
- Whisper transcription and error handling
- POST /api/sessions/{session_id}/answer-recording endpoint
- Live session inactivity timeout abandonment
- Async session deadline expiration check
"""
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from bson import ObjectId

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import get_db
from app.interview.media import check_ffmpeg_available, upload_recording, transcribe_recording
from main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    db = get_db()
    db.sessions.delete_many({
        "$or": [
            {"candidate.email": {"$regex": r"@(test|example)\.com$"}},
            {"candidate.name": {"$regex": r"(Test|Mock|Jane Doe)"}},
            {"is_test": True}
        ]
    })
    yield
    db.sessions.delete_many({
        "$or": [
            {"candidate.email": {"$regex": r"@(test|example)\.com$"}},
            {"candidate.name": {"$regex": r"(Test|Mock|Jane Doe)"}},
            {"is_test": True}
        ]
    })

@pytest.fixture(autouse=True)
def mock_ai_chains():
    """Mocks AI generation and evaluation chains."""
    mock_skills = {"skills": [{"skill": "Python", "weight": 1.0}], "mock": False}
    mock_bg = {"background": {"Python": "5 years experience"}, "mock": False}
    mock_qs = {
        "questions": [
            {"text": "What is Python GIL?", "skill_tag": "Python", "difficulty": "easy"},
            {"text": "Explain Python generators.", "skill_tag": "Python", "difficulty": "medium"}
        ],
        "mock": False
    }
    mock_eval = {
        "score": 8.0,
        "reasoning": "Accurate response.",
        "red_flag": False,
        "eval_provider": "groq",
        "mock": False
    }
    mock_summary = {
        "summary": "Candidate performed well.",
        "strengths": ["Python concurrency"],
        "weaknesses": [],
        "recommendation": "pass",
        "eval_provider": "groq",
        "mock": False
    }

    with patch("app.interview.service.extract_skills_from_jd", return_value=mock_skills), \
         patch("app.interview.service.extract_candidate_background", return_value=mock_bg), \
         patch("app.interview.service.generate_questions", return_value=mock_qs), \
         patch("app.interview.service.evaluate_answer", return_value=mock_eval), \
         patch("app.interview.service.generate_summary", return_value=mock_summary):
        yield


def test_ffmpeg_check():
    """Test that FFmpeg is detected on the system."""
    available = check_ffmpeg_available()
    assert available is True


def test_upload_recording_file():
    """Test saving an uploaded media file."""
    rel_path = upload_recording("session_test_123", "q1", b"dummy audio content", "test_audio.webm")
    full_path = Path(backend_dir) / rel_path
    assert full_path.exists()
    assert "session_test_123" in rel_path
    assert rel_path.startswith("uploads/recordings/")


def test_transcribe_error_handling():
    """Test transcribe_recording error handling when Whisper cannot process the file."""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(b"dummy corrupted audio content")
        temp_path = f.name

    try:
        with patch("app.interview.media.get_whisper_model", side_effect=Exception("Simulated whisper load error")):
            with pytest.raises(HTTPException) as exc_info:
                transcribe_recording(temp_path)
            assert exc_info.value.status_code == 500
    finally:
        if Path(temp_path).exists():
            Path(temp_path).unlink()


def test_submit_answer_recording_flow():
    """Test the POST /api/sessions/{session_id}/answer-recording endpoint."""
    # 1. Create a session with video capture type
    create_res = client.post(
        "/api/sessions",
        data={
            "candidate_name": "Jordan Lee",
            "candidate_email": "jordan@example.com",
            "jd_text": "Looking for a Python developer with experience in building web applications and FastAPI services.",
            "interview_mode": "live",
            "answer_capture_type": "video"
        },
        files={"resume_file": ("resume.txt", b"Python Developer with 4 years experience in FastAPI and web backend systems.", "text/plain")}
    )
    assert create_res.status_code == 201
    session_id = create_res.json()["session_id"]
    assert create_res.json()["interview_mode"] == "live"
    assert create_res.json()["answer_capture_type"] == "video"

    # 2. Get next question
    next_q = client.get(f"/api/sessions/{session_id}/next-question")
    assert next_q.status_code == 200
    q_data = next_q.json()["question"]
    assert q_data is not None
    question_id = q_data["id"]

    # 3. Submit answer recording
    with patch("app.interview.media.transcribe_recording", return_value={"text": "The GIL is the Global Interpreter Lock in CPython.", "confidence": 0.95, "transcription_mode": "real"}):
        ans_res = client.post(
            f"/api/sessions/{session_id}/answer-recording",
            data={"question_id": question_id, "duration_seconds": 15},
            files={"recording_file": ("answer_1.webm", b"dummy audio recording bytes " * 10, "video/webm")}
        )
        assert ans_res.status_code == 200
        data = ans_res.json()
        assert data["score"] == 8.0
        assert data["answer_source"] == "video"
        assert data["transcription_mode"] == "real"
        assert data["transcription_confidence"] == 0.95
        assert "uploads/recordings/" in data["recording_url"]


def test_async_session_deadline_expiration():
    """Test that submitting to an async session past its deadline returns 403."""
    db = get_db()
    
    # Create async session
    create_res = client.post(
        "/api/sessions",
        data={
            "candidate_name": "Async Tester",
            "candidate_email": "async@example.com",
            "jd_text": "Looking for a Python developer with experience in building web applications and FastAPI services.",
            "interview_mode": "async",
            "answer_capture_type": "text"
        },
        files={"resume_file": ("resume.txt", b"Python Developer with experience in backend services.", "text/plain")}
    )
    assert create_res.status_code == 201
    session_id = create_res.json()["session_id"]
    assert create_res.json()["interview_mode"] == "async"
    assert create_res.json()["session_deadline"] is not None

    # Manually expire the deadline in DB
    past_deadline = datetime.now(timezone.utc) - timedelta(days=1)
    db.sessions.update_one({"_id": ObjectId(session_id)}, {"$set": {"session_deadline": past_deadline}})

    # Next question attempt should be rejected with 403
    q_res = client.get(f"/api/sessions/{session_id}/next-question")
    assert q_res.status_code == 403
    assert "expired" in q_res.json()["detail"].lower()


def test_live_session_abandonment_timeout():
    """Test that an inactive live session is marked abandoned and returns 403."""
    db = get_db()

    create_res = client.post(
        "/api/sessions",
        data={
            "candidate_name": "Live Tester",
            "candidate_email": "live@example.com",
            "jd_text": "Looking for a Python developer with experience in building web applications and FastAPI services.",
            "interview_mode": "live",
            "answer_capture_type": "text"
        },
        files={"resume_file": ("resume.txt", b"Python Developer with experience in backend services.", "text/plain")}
    )
    assert create_res.status_code == 201
    session_id = create_res.json()["session_id"]

    # Retrieve question id
    next_q = client.get(f"/api/sessions/{session_id}/next-question")
    assert next_q.status_code == 200
    question_id = next_q.json()["question"]["id"]

    # Manually backdate last_active_at in DB past the 60-minute limit
    stale_active_time = datetime.now(timezone.utc) - timedelta(minutes=75)
    db.sessions.update_one({"_id": ObjectId(session_id)}, {"$set": {"last_active_at": stale_active_time}})

    # Next interaction should trigger abandonment and return 403
    ans_res = client.post(
        f"/api/sessions/{session_id}/answer",
        json={"question_id": question_id, "answer_text": "Testing timeout handling."}
    )
    assert ans_res.status_code == 403
    assert "abandoned" in ans_res.json()["detail"].lower()
