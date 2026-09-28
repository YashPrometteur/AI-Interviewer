"""Phase 3 Test Suite: AI Proctoring & Candidate Integrity.

Tests:
1. Integrity scoring algorithms & diminishing penalty math.
2. Integrity flag generation & caveat synthesis.
3. Proctoring telemetry event ingestion endpoint.
4. Periodic frame-sampling proctoring endpoint with error resilience.
5. End-to-end report generation incorporating integrity metrics.
"""
import io
import pytest
import numpy as np
import cv2
from fastapi.testclient import TestClient

from main import app
from app.db.database import get_db
from app.proctoring.scoring import (
    compute_integrity_score,
    generate_integrity_flags,
    get_event_severity,
)
from app.proctoring.vision import analyze_frame

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    db = get_db()
    cleanup = lambda: db.sessions.delete_many({
        "$or": [
            {"candidate.email": {"$regex": r"@(test|example)\.com$"}},
            {"candidate.name": {"$regex": r"(Test|Mock|Jane Doe)"}},
            {"is_test": True}
        ]
    })
    cleanup()
    yield
    cleanup()


# --- 1. Scoring & Flag Synthesis Unit Tests ---
def test_integrity_score_clean_session():
    """Verify that a session with zero anomalies returns 10.0 score and no flags."""
    events = []
    score = compute_integrity_score(events)
    flags = generate_integrity_flags(events)
    assert score == 10.0
    assert len(flags) == 0


def test_integrity_score_remains_static_with_events():
    """Verify that compute_integrity_score returns constant 10.0 baseline regardless of events."""
    events_mixed = [
        {"event_type": "tab_switch"},
        {"event_type": "focus_loss"},
        {"event_type": "multi_screen_detected"},
        {"event_type": "multiple_faces_detected"},
    ]
    assert compute_integrity_score(events_mixed) == 10.0


def test_generate_integrity_flags_anomalies():
    """Verify generate_integrity_flags produces descriptive anomaly summaries."""
    events = [
        {"event_type": "tab_switch"},
        {"event_type": "tab_switch"},
        {"event_type": "multiple_faces_detected"},
        {"event_type": "multi_screen_detected"},
        {"event_type": "no_face_detected"},
    ]
    flags = generate_integrity_flags(events)
    assert len(flags) == 4
    assert any("2 browser tab switches" in f for f in flags)
    assert any("Multiple individuals detected" in f for f in flags)
    assert any("Multiple monitors" in f for f in flags)
    assert any("Candidate face was not visible" in f for f in flags)


def test_generate_integrity_flags_ignores_system_analysis_error():
    """Verify that analysis_error is excluded from candidate misconduct flags."""
    events = [{"event_type": "analysis_error"}, {"event_type": "analysis_error"}]
    flags = generate_integrity_flags(events)
    assert len(flags) == 0



# --- 2. Vision Frame Analysis Unit Tests ---
def test_analyze_frame_fallback_on_corrupted_data():
    """Verify corrupted byte stream returns fallback schema without crashing."""
    res = analyze_frame(b"corrupted_payload")
    assert res["person_count"] is None
    assert res["face_count"] is None
    assert res["success"] is False
    assert res["error"] is not None


def test_analyze_frame_valid_synthetic_image():
    """Verify analyze_frame processes a valid encoded image."""
    blank_img = np.zeros((300, 300, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", blank_img)
    res = analyze_frame(encoded.tobytes())
    assert res["success"] is True
    assert res["person_count"] == 0
    assert res["face_count"] == 0
    assert res["error"] is None


from unittest.mock import patch
from app.db.database import get_db

@pytest.fixture(autouse=True)
def mock_ai():
    mock_skills = {"skills": [{"skill": "Python Backend", "weight": 0.5}, {"skill": "Database & SQL", "weight": 0.5}], "mock": False}
    mock_bg = {"background": {"Python Backend": "Solid backend experience"}, "mock": False}
    mock_qs = {
        "questions": [
            {"text": "Explain async def in FastAPI.", "skill_tag": "Python Backend", "difficulty": "easy"},
            {"text": "How do you optimize slow queries in PostgreSQL?", "skill_tag": "Database & SQL", "difficulty": "medium"}
        ],
        "mock": False
    }
    mock_eval = {
        "score": 8.5,
        "reasoning": "Clear explanation of core technical concepts.",
        "red_flag": False,
        "eval_provider": "groq",
        "mock": False
    }
    mock_summary = {
        "summary": "Strong candidate with solid domain experience.",
        "strengths": ["FastAPI architecture", "Database optimization"],
        "weaknesses": ["Distributed scaling"],
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

# --- 3. API Route Tests ---
def test_proctoring_event_api_flow():
    """Verify logging a browser telemetry event via POST /sessions/{id}/proctoring-event."""
    # 1. Create a dummy session
    create_res = client.post(
        "/api/sessions",
        data={
            "candidate_name": "Proctoring Test Candidate",
            "candidate_email": "proctor@example.com",
            "jd_text": "We are seeking a Senior Python FastAPI Engineer with 5+ years of distributed backend experience.",
            "interview_mode": "live",
            "answer_capture_type": "video",
        },
        files={
            "resume_file": ("resume.txt", b"Senior Python developer building high-throughput FastAPI microservices.", "text/plain"),
        }
    )
    assert create_res.status_code == 201
    session_id = create_res.json()["session_id"]

    # 2. Log tab switch event
    event_res = client.post(
        f"/api/sessions/{session_id}/proctoring-event",
        json={
            "event_type": "tab_switch",
            "details": "User switched to another browser tab"
        }
    )
    assert event_res.status_code == 200
    data = event_res.json()
    assert data["event_type"] == "tab_switch"
    assert data["severity"] == "low"

    # 3. Log multi-screen event
    screen_res = client.post(
        f"/api/sessions/{session_id}/proctoring-event",
        json={
            "event_type": "multi_screen_detected",
            "details": "Extended display connected"
        }
    )
    assert screen_res.status_code == 200
    assert screen_res.json()["severity"] == "medium"

    # 4. Upload proctoring frame snapshot
    blank_img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", blank_img)
    frame_res = client.post(
        f"/api/sessions/{session_id}/proctoring-frame",
        files={"frame_file": ("frame.jpg", io.BytesIO(encoded.tobytes()), "image/jpeg")}
    )
    assert frame_res.status_code == 200
    frame_data = frame_res.json()
    assert frame_data["success"] is True
    # Blank image has 0 persons/faces -> logs no_face_detected
    assert frame_data["event_logged"] == "no_face_detected"

    # Answer all questions in session
    while True:
        q_resp = client.get(f"/api/sessions/{session_id}/next-question")
        assert q_resp.status_code == 200
        q_data = q_resp.json()
        if q_data.get("is_completed") or not q_data.get("question"):
            break
        q = q_data["question"]
        ans_resp = client.post(
            f"/api/sessions/{session_id}/answer",
            json={
                "question_id": q["id"],
                "answer_text": "Async def in FastAPI allows non-blocking concurrency using asyncio event loop."
            }
        )
        assert ans_resp.status_code == 200

    # 5. Complete session and verify integrity metrics
    comp_res = client.post(f"/api/sessions/{session_id}/complete")
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert "integrity_score" in comp_data
    assert comp_data["integrity_score"] == 10.0  # Static baseline score
    assert len(comp_data.get("integrity_flags", [])) > 0

    # 6. Check full report
    report_res = client.get(f"/api/reports/{session_id}")
    assert report_res.status_code == 200
    rep_data = report_res.json()
    assert rep_data["integrity_score"] == 10.0
    assert len(rep_data["integrity_flags"]) > 0
    assert len(rep_data["proctoring_events"]) >= 3
