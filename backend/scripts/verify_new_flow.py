"""Verification script for the new interview flow:
1. Dynamic difficulty & per-question recording
2. Continuous full session video upload & storage
3. Malpractice warning proof screenshots & second-level timestamps in reports
"""
import io
import os
import sys
import base64
from fastapi.testclient import TestClient

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from app.db.database import get_db

client = TestClient(app)

def run_verification():
    print("=" * 70)
    print("🚀 VERIFYING NEW INTERVIEW FLOW & REPORT ENHANCEMENTS")
    print("=" * 70)

    # 1. Create a live session with video capture type
    print("\n1. Creating live interview session...")
    jd = "Senior React and Python Engineer with 5+ years building distributed cloud microservices."
    dummy_resume = io.BytesIO(
        b"Sarah Connor - Lead Full Stack Engineer. 8+ years developing highly scalable cloud solutions with React, TypeScript, FastAPI, Python, Docker, Kubernetes, and MongoDB. Proven track record leading agile engineering squads."
    )
    res = client.post(
        "/api/sessions",
        data={
            "candidate_name": "Sarah Connor",
            "candidate_email": "sarah.connor@sky.net",
            "jd_text": jd,
            "interview_mode": "live",
            "answer_capture_type": "video",
        },
        files={"resume_file": ("resume.txt", dummy_resume, "text/plain")}
    )
    assert res.status_code in (200, 201), f"Failed to create session: {res.text}"
    session_data = res.json()
    session_id = session_data["session_id"]
    print(f"   ✓ Session created: {session_id}")
    print(f"   ✓ Total questions generated: {session_data['total_questions']}")

    # 2. Fetch first question and verify difficulty
    print("\n2. Fetching question 1...")
    q_res = client.get(f"/api/sessions/{session_id}/next-question")
    assert q_res.status_code == 200, f"Failed to get question: {q_res.text}"
    q_data = q_res.json()
    q = q_data["question"]
    assert q is not None, "Question is None"
    print(f"   ✓ Question 1: '{q['text'][:60]}...'")
    print(f"   ✓ Difficulty: {q['difficulty']} (Timer: {'120s' if q['difficulty'] == 'easy' else '180s' if q['difficulty'] == 'medium' else '300s'})")

    # 3. Simulate continuous master session video upload
    print("\n3. Testing continuous master session video upload...")
    dummy_video_bytes = b"FAKE_WEBM_VIDEO_DATA_HEADER_AND_FRAMES_FOR_SESSION"
    vid_res = client.post(
        f"/api/sessions/{session_id}/session-video",
        files={"video_file": ("session_master_recording.webm", dummy_video_bytes, "video/webm")},
    )
    assert vid_res.status_code == 200, f"Failed to upload session video: {vid_res.text}"
    vid_data = vid_res.json()
    assert "session_video_url" in vid_data, "session_video_url missing from upload response"
    print(f"   ✓ Full session video saved: {vid_data['session_video_url']}")

    # 4. Simulate a malpractice warning with proof screenshot & seconds timestamp
    print("\n4. Testing malpractice event logging with screenshot proof...")
    # Generate a 1x1 synthetic PNG in base64
    tiny_png_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    event_res = client.post(
        f"/api/sessions/{session_id}/proctoring-event",
        json={
            "event_type": "tab_switch",
            "severity": "medium",
            "question_id": q["id"],
            "details": "Candidate switched away from the active interview tab",
            "screenshot_base64": tiny_png_b64,
        }
    )
    assert event_res.status_code == 200, f"Failed to log proctoring event: {event_res.text}"
    event_data = event_res.json()
    print(f"   ✓ Proctoring event logged: {event_data['event_type']}")
    print(f"   ✓ Formatted timestamp (with seconds): {event_data.get('formatted_timestamp')}")
    print(f"   ✓ Proof screenshot URL: {event_data.get('screenshot_url')}")
    assert event_data.get("screenshot_url") is not None, "Screenshot proof URL was not saved!"
    assert ":" in event_data.get("formatted_timestamp", ""), "Timestamp missing second precision!"

    # 5. Answer questions and complete session
    print("\n5. Submitting answers for interview questions...")
    # Answer question 1
    ans1_res = client.post(
        f"/api/sessions/{session_id}/answer",
        json={"question_id": q["id"], "answer_text": "I manage state using React context and useReducer for global state with memoization to prevent unnecessary re-renders."}
    )
    assert ans1_res.status_code == 200, f"Failed to submit answer 1: {ans1_res.text}"
    print("   ✓ Question 1 answered")

    # Fetch and answer question 2
    q2_res = client.get(f"/api/sessions/{session_id}/next-question")
    if q2_res.status_code == 200 and q2_res.json().get("question"):
        q2 = q2_res.json()["question"]
        client.post(f"/api/sessions/{session_id}/answer", json={"question_id": q2["id"], "answer_text": "We implement robust error boundaries and async retry mechanisms."})
        print("   ✓ Question 2 answered")

    # Fetch and answer question 3
    q3_res = client.get(f"/api/sessions/{session_id}/next-question")
    if q3_res.status_code == 200 and q3_res.json().get("question"):
        q3 = q3_res.json()["question"]
        client.post(f"/api/sessions/{session_id}/answer", json={"question_id": q3["id"], "answer_text": "High availability is achieved through clustering, read replicas, and caching."})
        print("   ✓ Question 3 answered")

    print("\n6. Finalizing session and verifying comprehensive recruiter report...")
    comp_res = client.post(f"/api/sessions/{session_id}/complete")
    assert comp_res.status_code == 200, f"Failed to complete session: {comp_res.text}"

    rep_res = client.get(f"/api/reports/{session_id}")
    assert rep_res.status_code == 200, f"Failed to get full report: {rep_res.text}"
    rep = rep_res.json()

    print("\n" + "=" * 70)
    print("📊 FULL RECRUITER REPORT VERIFICATION")
    print("=" * 70)
    print(f"   Candidate Name:       {rep['candidate_name']}")
    print(f"   Candidate Email:      {rep['candidate_email']}")
    print(f"   Session ID:           {rep['session_id']}")
    print(f"   Session Video URL:    {rep['session_video_url']}")
    print(f"   Overall Score:        {rep['overall_score']}")
    print(f"   Integrity Score:      {rep['integrity_score']}")
    print(f"   Total Questions:      {len(rep['transcript'])}")
    print(f"   Proctoring Events:    {len(rep['proctoring_events'])}")

    for idx, pe in enumerate(rep['proctoring_events']):
        print(f"     [{idx+1}] {pe['event_type']} @ {pe['formatted_timestamp']} | Proof: {pe['screenshot_url']}")

    assert rep["candidate_name"] == "Sarah Connor"
    assert rep["session_video_url"] is not None, "session_video_url is missing from report"
    assert len(rep["proctoring_events"]) > 0, "No proctoring events found in report"
    assert rep["proctoring_events"][0]["screenshot_url"] is not None, "Proof screenshot missing from report event"

    print("\n✅ ALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_verification()
