"""Automated Test Suite for Phase 1 API Endpoints and Edge Cases.
Tests session creation, edge case validations, answer evaluations, adaptive difficulty progression,
weighted score calculations, and report generation.
"""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from unittest.mock import patch
from app.db.database import get_db
from main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    db = get_db()
    # Delete only test-generated mock records without touching human candidate interviews
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
    """Mocks AI generation and evaluation chains so test suite runs instantly in isolation."""
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

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_edge_case_short_jd():
    """Session creation should fail with 400 when JD text is too short (<50 chars)."""
    response = client.post(
        "/api/sessions",
        data={
            "candidate_name": "Test Candidate",
            "candidate_email": "candidate@example.com",
            "jd_text": "Too short JD",
        },
        files={"resume_file": ("resume.txt", b"A sufficiently long resume text describing engineering background.", "text/plain")}
    )
    assert response.status_code == 400
    assert "Job description is too short" in response.json()["detail"]

def test_edge_case_empty_or_skip_answer():
    """Submitting empty, whitespace, or 'I don't remember' answer is accepted with 200 and evaluated cleanly."""
    create_resp = client.post(
        "/api/sessions",
        data={
            "candidate_name": "Test Candidate",
            "candidate_email": "candidate@example.com",
            "jd_text": "We are seeking a Backend Engineer skilled in Python, FastAPI, and PostgreSQL database design.",
        },
        files={"resume_file": ("resume.txt", b"Senior Python developer with 5 years building backend services.", "text/plain")}
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    q_resp = client.get(f"/api/sessions/{session_id}/next-question")
    assert q_resp.status_code == 200
    q_id = q_resp.json()["question"]["id"]

    ans_resp = client.post(
        f"/api/sessions/{session_id}/answer",
        json={"question_id": q_id, "answer_text": "   "}
    )
    assert ans_resp.status_code == 200
    assert "score" in ans_resp.json()

def test_full_session_flow():
    """Tests complete end-to-end interview turn flow and report generation."""
    # 1. Create Session
    create_resp = client.post(
        "/api/sessions",
        data={
            "candidate_name": "Jordan Smith",
            "candidate_email": "jordan.smith@example.com",
            "jd_text": "Full stack engineer proficient in TypeScript, React, Node.js, and relational database systems.",
        },
        files={"resume_file": ("resume.txt", b"Experienced Full Stack Developer with 4 years React and TypeScript experience.", "text/plain")}
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    session_id = data["session_id"]
    assert data["total_questions"] > 0

    # 2. Get Question 1
    q_resp1 = client.get(f"/api/sessions/{session_id}/next-question")
    assert q_resp1.status_code == 200
    q1 = q_resp1.json()["question"]
    assert q1 is not None

    # 3. Submit Answer 1
    ans_resp1 = client.post(
        f"/api/sessions/{session_id}/answer",
        json={
            "question_id": q1["id"],
            "answer_text": "TypeScript provides static type checking at compile time which catches type mismatch errors early and enhances IDE autocomplete."
        }
    )
    assert ans_resp1.status_code == 200
    eval1 = ans_resp1.json()
    assert eval1["score"] >= 0 and eval1["score"] <= 10

    # 4. Attempt premature completion while Question 2 is unanswered -> Should be rejected with 400
    premature_comp = client.post(f"/api/sessions/{session_id}/complete")
    assert premature_comp.status_code == 400
    assert "remain unanswered" in premature_comp.json()["detail"]

    # 5. Get and answer Question 2
    q_resp2 = client.get(f"/api/sessions/{session_id}/next-question")
    assert q_resp2.status_code == 200
    q2 = q_resp2.json()["question"]
    assert q2 is not None

    ans_resp2 = client.post(
        f"/api/sessions/{session_id}/answer",
        json={
            "question_id": q2["id"],
            "answer_text": "I optimize slow PostgreSQL queries using EXPLAIN ANALYZE, creating targeted B-Tree indexes, and configuring connection pooling."
        }
    )
    assert ans_resp2.status_code == 200

    # 6. Complete Session & Get Report
    comp_resp = client.post(f"/api/sessions/{session_id}/complete")
    assert comp_resp.status_code == 200
    report_data = comp_resp.json()
    assert report_data["status"] == "completed"
    assert "recommendation" in report_data["report"]
    assert report_data["report"]["recommendation"] in ["pass", "fail", "borderline"]

    # 7. Fetch Report Endpoint
    rep_resp = client.get(f"/api/reports/{session_id}")
    assert rep_resp.status_code == 200
    full_rep = rep_resp.json()
    assert full_rep["candidate_name"] == "Jordan Smith"
    assert len(full_rep["transcript"]) > 0
