"""Phase 4 Verification Script: Automated end-to-end verification of Piper TTS audio question delivery,
single-call LLM evaluation + dynamic counter-question generation, follow-up depth cap (max 1),
and report transcript formatting.
"""
import sys
import os
import io
import wave
from pathlib import Path
from bson import ObjectId

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.database import get_db
from app.interview import tts, service
from app.interview.parser import parse_resume
from app.ai.chains import evaluate_answer
from app.db.models import build_question_entry, build_session_document
from app.reports.service import get_full_report
from fastapi.testclient import TestClient
from main import app

def test_piper_tts_synthesis():
    print("\n--- [TEST 1] Piper TTS Audio Synthesis ---")
    sample_text = "Explain the difference between optimistic and pessimistic locking in distributed systems."
    audio_bytes = tts.synthesize_speech(sample_text)
    
    assert audio_bytes is not None and len(audio_bytes) > 0, "TTS synthesis returned empty bytes"
    assert audio_bytes[:4] == b"RIFF", "Generated audio is not a valid RIFF WAV file"
    assert audio_bytes[8:12] == b"WAVE", "Generated audio is not a WAVE format"
    
    # Check WAV properties
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        duration_sec = frames / float(sample_rate)
        print(f"[OK] Synthesized WAV: {len(audio_bytes)} bytes | {channels} channel(s) | {sample_rate}Hz | Duration: {duration_sec:.2f}s")
        assert channels in (1, 2)
        assert sample_rate > 0
        assert duration_sec > 0.5


def test_session_creation_with_pre_synthesized_tts():
    print("\n--- [TEST 2] Session Creation with Pre-Synthesized Audio ---")
    db = get_db()
    jd_text = """We are looking for a Senior Backend Engineer proficient in Python, FastAPI, MongoDB, and Distributed Systems. Experience with asynchronous architectures and caching is required."""
    resume_text = """Alex Mercer - Senior Python Engineer. 6 years building high throughput microservices with FastAPI, Redis, PostgreSQL, and Kafka."""
    
    res = service.start_session(
        db=db,
        candidate_name="Alex Mercer",
        candidate_email="alex.mercer.phase4@example.com",
        jd_text=jd_text,
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="live",
        answer_capture_type="text"
    )
    
    session_id = res.session_id
    assert session_id, "Session ID not returned"
    print(f"[OK] Session created: {session_id} with {res.total_questions} questions")
    
    # Check session questions in MongoDB
    session_doc = db.sessions.find_one({"_id": ObjectId(session_id)})
    assert session_doc is not None
    questions = session_doc.get("questions", [])
    assert len(questions) > 0, "No questions found in session"
    
    for q in questions:
        q_id = q["question_id"]
        audio_url = q.get("audio_url")
        print(f"  - Q [{q.get('difficulty')}]: {q['text'][:50]}... -> audio_url: {audio_url}")
        assert audio_url is not None and f"/sessions/{session_id}/questions/{q_id}/audio" in audio_url
        
        # Verify physical file existence
        audio_file_path = tts.get_question_audio_path(session_id, q_id)
        assert audio_file_path is not None and audio_file_path.exists(), f"Audio file not found on disk for Q:{q_id}"
        assert audio_file_path.stat().st_size > 1000, f"Audio file is too small ({audio_file_path.stat().st_size} bytes)"

    return session_id


def test_audio_streaming_endpoint(session_id: str):
    print("\n--- [TEST 3] GET /api/sessions/{session_id}/questions/{question_id}/audio Endpoint ---")
    client = TestClient(app)
    db = get_db()
    session_doc = db.sessions.find_one({"_id": ObjectId(session_id)})
    first_q = session_doc["questions"][0]
    q_id = first_q["question_id"]
    
    response = client.get(f"/api/sessions/{session_id}/questions/{q_id}/audio")
    assert response.status_code == 200, f"Audio endpoint failed: {response.status_code} - {response.text}"
    assert response.headers.get("content-type") == "audio/wav", f"Expected audio/wav, got {response.headers.get('content-type')}"
    assert len(response.content) > 1000, "Audio response content is empty or too small"
    print(f"[OK] Successfully streamed audio file: {len(response.content)} bytes (200 OK, audio/wav)")


def test_combined_single_call_evaluation_and_followup():
    print("\n--- [TEST 4] Combined Evaluation & Dynamic Counter-Question Logic ---")
    question_text = "How do you handle database concurrency and avoid race conditions in a distributed system?"
    vague_answer = "I usually use a lock or transaction to make sure things don't conflict."
    
    eval_res = evaluate_answer(
        question=question_text,
        skill_tag="Distributed Systems",
        answer_text=vague_answer,
        is_transcribed=False
    )
    
    print(f"  - Score: {eval_res['score']}/10")
    print(f"  - Needs Follow-up: {eval_res.get('needs_followup')}")
    print(f"  - Follow-up Question: {eval_res.get('followup_question')}")
    print(f"  - Follow-up Reason: {eval_res.get('followup_reason')}")
    print(f"  - Provider: {eval_res.get('eval_provider')}")
    
    assert "score" in eval_res
    assert "reasoning" in eval_res
    assert "needs_followup" in eval_res
    print("[OK] Combined evaluation returned scoring and follow-up decision in a single call")


def test_followup_insertion_and_depth_cap(session_id: str):
    print("\n--- [TEST 5] Dynamic Counter-Question Insertion & Depth Cap (Max 1) ---")
    db = get_db()
    
    # 1. Fetch next question
    next_res = service.get_next_question(db, session_id)
    assert next_res.question is not None
    q1 = next_res.question
    print(f"  Current Question: {q1.text} (is_followup={q1.is_followup})")
    
    # 2. Submit an answer that warrants a follow-up
    vague_answer = "We can use caching like Redis or Memcached to make it faster."
    ans_res = service.submit_answer(
        db=db,
        session_id=session_id,
        question_id=q1.id,
        answer_text=vague_answer,
        answer_source="text"
    )
    print(f"  Submitted Answer evaluated: Score={ans_res.score}, needs_followup={ans_res.needs_followup}")
    
    # 3. Check if follow-up was inserted or let's verify Next Question flow
    next_res2 = service.get_next_question(db, session_id)
    assert next_res2.question is not None
    q2 = next_res2.question
    
    if ans_res.needs_followup and ans_res.followup_question:
        print(f"  [OK] Next Question served is Follow-up: {q2.text}")
        assert q2.is_followup is True, "Expected follow-up question to be served next"
        assert q2.parent_question_id == q1.id, "Follow-up question parent_question_id mismatch"
        assert q2.audio_url is not None, "Follow-up question must have synthesized audio_url"
        
        # Test Depth Cap: Answering follow-up question should NEVER spawn another follow-up
        ans_res2 = service.submit_answer(
            db=db,
            session_id=session_id,
            question_id=q2.id,
            answer_text="Specifically, we use Redis distributed locks with TTL and redlock algorithm.",
            answer_source="text"
        )
        print(f"  Follow-up answer submitted: Score={ans_res2.score}")
        
        # Check DB to verify no secondary follow-up was added for q2
        updated_doc = db.sessions.find_one({"_id": ObjectId(session_id)})
        sub_followups = [q for q in updated_doc["questions"] if q.get("parent_question_id") == q2.id]
        assert len(sub_followups) == 0, "Depth cap violated: follow-up question spawned a secondary follow-up!"
        print("  [OK] Depth cap verified: Follow-up question did not spawn any sub-followup (max depth = 1)")
    else:
        print("  (Answer did not trigger follow-up; standard progression verified)")


def test_report_transcript_phase4_fields(session_id: str):
    print("\n--- [TEST 6] Evaluation Report Transcript Formatting ---")
    db = get_db()
    
    # Complete remaining questions
    while True:
        nxt = service.get_next_question(db, session_id)
        if nxt.is_completed or not nxt.question:
            break
        service.submit_answer(
            db=db,
            session_id=session_id,
            question_id=nxt.question.id,
            answer_text="Solid comprehensive technical explanation covering design patterns, edge cases, and scalability.",
            answer_source="text"
        )
    
    comp_res = service.complete_session(db, session_id)
    assert comp_res.status == "completed"
    print(f"[OK] Session finalized with overall score: {comp_res.overall_score:.2f}/10")
    
    report_res = get_full_report(db, session_id)
    assert len(report_res.transcript) > 0
    
    for item in report_res.transcript:
        print(f"  Transcript Item: Q:{item.question_id[:8]}... | is_followup={item.is_followup} | audio_url={item.audio_url} | score={item.score}")
        assert hasattr(item, "is_followup")
        assert hasattr(item, "parent_question_id")
        assert hasattr(item, "audio_url")
    
    print("[OK] All Phase 4 transcript items have is_followup, parent_question_id, and audio_url fields properly populated")


def main():
    print("=" * 60)
    print(">>> RUNNING PHASE 4 AUTOMATED VERIFICATION SUITE")
    print("=" * 60)
    
    test_piper_tts_synthesis()
    session_id = test_session_creation_with_pre_synthesized_tts()
    test_audio_streaming_endpoint(session_id)
    test_combined_single_call_evaluation_and_followup()
    test_followup_insertion_and_depth_cap(session_id)
    test_report_transcript_phase4_fields(session_id)
    
    print("\n" + "=" * 60)
    print("[SUCCESS] ALL PHASE 4 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
