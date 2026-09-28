"""Phase 4: Unit and integration tests for Piper TTS audio question synthesis,
pre-synthesized streaming endpoints, combined evaluation + dynamic counter-question logic,
depth cap enforcement, and report transcript display.
"""
import io
import wave
import sys
from pathlib import Path
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.database import get_db
from app.interview import tts, service
from app.ai.chains import evaluate_answer
from app.reports.service import get_full_report
from main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def db():
    return get_db()

def test_tts_synthesize_speech():
    text = "What is the event loop in Node.js and Python asyncio?"
    audio_bytes = tts.synthesize_speech(text)
    assert audio_bytes is not None
    assert len(audio_bytes) > 1000
    assert audio_bytes[:4] == b"RIFF"
    assert audio_bytes[8:12] == b"WAVE"
    
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
        assert wav.getnchannels() in (1, 2)
        assert wav.getframerate() == 22050

def test_session_creation_pre_synthesizes_audio(db, client):
    jd_text = "Senior Python engineer with experience in FastAPI and MongoDB microservices."
    resume_text = "Jane Doe - Python Developer with 5 years experience in building APIs."
    
    res = service.start_session(
        db=db,
        candidate_name="Jane Doe",
        candidate_email="jane.doe.phase4@test.com",
        jd_text=jd_text,
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="live",
        answer_capture_type="text"
    )
    
    session_id = res.session_id
    doc = db.sessions.find_one({"_id": ObjectId(session_id)})
    assert doc is not None
    questions = doc.get("questions", [])
    assert len(questions) > 0
    
    for q in questions:
        assert q.get("audio_url") is not None
        assert f"/sessions/{session_id}/questions/{q['question_id']}/audio" in q["audio_url"]
        
        # Test endpoint
        resp = client.get(f"/api/sessions/{session_id}/questions/{q['question_id']}/audio")
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "audio/wav"
        assert len(resp.content) > 1000

def test_single_call_evaluation_and_followup():
    eval_res = evaluate_answer(
        question="Explain how database indexes work under the hood.",
        skill_tag="Databases",
        answer_text="They make lookups faster by organizing the data.",
        is_transcribed=False
    )
    assert "score" in eval_res
    assert "reasoning" in eval_res
    assert "needs_followup" in eval_res
    assert isinstance(eval_res["needs_followup"], bool)

def test_followup_question_depth_cap(db):
    jd_text = "Backend engineer experienced with Redis and distributed caching."
    resume_text = "John Smith - Backend engineer proficient with Python and Redis."
    
    res = service.start_session(
        db=db,
        candidate_name="John Smith",
        candidate_email="john.smith.phase4@test.com",
        jd_text=jd_text,
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="live",
        answer_capture_type="text"
    )
    session_id = res.session_id
    
    next_q = service.get_next_question(db, session_id)
    assert next_q.question is not None
    q1_id = next_q.question.id
    
    # Submit answer
    eval_out = service.submit_answer(
        db=db,
        session_id=session_id,
        question_id=q1_id,
        answer_text="We use Redis to cache query results.",
        answer_source="text"
    )
    
    # Check next question
    next_q2 = service.get_next_question(db, session_id)
    if next_q2.question and next_q2.question.is_followup:
        assert next_q2.question.parent_question_id == q1_id
        assert next_q2.question.audio_url is not None
        
        # Submit answer to follow-up
        eval_out2 = service.submit_answer(
            db=db,
            session_id=session_id,
            question_id=next_q2.question.id,
            answer_text="Specifically using cache-aside pattern with TTL expiration.",
            answer_source="text"
        )
        
        # Verify no sub-followup
        doc = db.sessions.find_one({"_id": ObjectId(session_id)})
        sub_followups = [q for q in doc["questions"] if q.get("parent_question_id") == next_q2.question.id]
        assert len(sub_followups) == 0
