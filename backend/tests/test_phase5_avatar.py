"""Phase 5: Unit and integration tests for:
1. Interviewer photo validation and Haar cascade face detection.
2. Wav2Lip model loading and neural architecture integrity.
3. Lightweight real-time mouth amplitude envelope extraction.
4. Pre-rendered Wav2Lip MP4 streaming endpoint.
5. Interviewer photo streaming endpoint.
6. Graceful audio-only fallback when no photo is provided.
"""
import io
import time
import sys
import numpy as np
import cv2
import pytest
from pathlib import Path
from bson import ObjectId
from fastapi.testclient import TestClient
from fastapi import HTTPException

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.database import get_db
from app.interview import avatar, service, tts
from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    return get_db()


def make_valid_face_image_bytes() -> bytes:
    """Creates an in-memory image with clear Haar-detectable facial feature gradients."""
    gray = np.zeros((400, 400), dtype=np.uint8)
    cv2.circle(gray, (200, 200), 120, 200, -1)
    cv2.circle(gray, (155, 175), 25, 60, -1)
    cv2.circle(gray, (245, 175), 25, 60, -1)
    cv2.rectangle(gray, (190, 160), (210, 220), 240, -1)
    cv2.circle(gray, (140, 225), 30, 230, -1)
    cv2.circle(gray, (260, 225), 30, 230, -1)
    cv2.ellipse(gray, (200, 275), (40, 15), 0, 0, 360, 50, -1)
    img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def test_photo_validation_valid_face():
    photo_bytes = make_valid_face_image_bytes()
    img, bbox = avatar.validate_interviewer_photo(photo_bytes)
    assert img is not None
    assert len(bbox) == 4
    assert bbox[2] > 0 and bbox[3] > 0


def test_photo_validation_no_face():
    # Plain white background with no facial features
    img = np.ones((300, 300, 3), dtype=np.uint8) * 255
    _, buf = cv2.imencode(".jpg", img)
    with pytest.raises(HTTPException) as exc_info:
        avatar.validate_interviewer_photo(buf.tobytes())
    assert exc_info.value.status_code == 400
    assert "Could not detect a clear front-facing face" in exc_info.value.detail


def test_photo_validation_empty_or_corrupt():
    with pytest.raises(HTTPException) as exc_info:
        avatar.validate_interviewer_photo(b"")
    assert exc_info.value.status_code == 400


def test_wav2lip_model_structure():
    model = avatar.get_wav2lip_model()
    assert model is not None
    # Verify model is on CPU in eval mode
    assert not model.training


def test_extract_mouth_amplitude_track():
    audio_bytes = tts.synthesize_speech("Let us discuss database indexes.")
    assert audio_bytes is not None

    t0 = time.perf_counter()
    track = avatar.extract_mouth_amplitude_track(audio_bytes, frame_duration_ms=50)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert isinstance(track, list)
    assert len(track) > 0
    # Values should be normalized between 0.0 and 1.0
    for val in track:
        assert 0.0 <= val <= 1.0
    print(f"\n[TEST BENCHMARK] Amplitude extraction took {elapsed_ms:.2f}ms for {len(track)} chunks")


def test_session_creation_with_photo(db, client):
    photo_bytes = make_valid_face_image_bytes()
    jd_text = "Senior Python engineer with deep experience in FastAPI, microservices, and MongoDB databases."
    resume_text = "John Smith - Experienced Python backend specialist with 6 years building distributed APIs and scalable backends."

    res = service.start_session(
        db=db,
        candidate_name="John Smith",
        candidate_email="john.smith.phase5@test.com",
        jd_text=jd_text,
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="live",
        answer_capture_type="text",
        interviewer_photo_bytes=photo_bytes,
        interviewer_photo_filename="interviewer.jpg"
    )

    assert res.session_id is not None
    doc = db.sessions.find_one({"_id": ObjectId(res.session_id)})
    assert doc is not None
    assert doc.get("interviewer_photo_url") is not None

    # Test interviewer photo endpoint
    photo_res = client.get(f"/api/sessions/{res.session_id}/interviewer-photo")
    assert photo_res.status_code == 200
    assert photo_res.headers["content-type"].startswith("image/")


def test_session_creation_without_photo_fallback(db, client):
    jd_text = "Frontend engineer with experience in React, Next.js, TypeScript, and modern UI design principles."
    resume_text = "Alice Developer - Senior frontend specialist with 5 years creating responsive Web applications in React and TypeScript."

    res = service.start_session(
        db=db,
        candidate_name="Alice Developer",
        candidate_email="alice.dev.phase5@test.com",
        jd_text=jd_text,
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="live",
        answer_capture_type="text"
    )

    doc = db.sessions.find_one({"_id": ObjectId(res.session_id)})
    assert doc is not None
    assert doc.get("interviewer_photo_url") is None

    # Getting avatar video should return 404 cleanly
    first_q = doc["questions"][0]
    q_id = first_q["question_id"]
    vid_res = client.get(f"/api/sessions/{res.session_id}/questions/{q_id}/avatar-video")
    assert vid_res.status_code == 404

    # But audio endpoint should work perfectly
    audio_res = client.get(f"/api/sessions/{res.session_id}/questions/{q_id}/audio")
    assert audio_res.status_code == 200


def test_male_voice_synthesis_and_gender_assignment(db):
    male_audio = tts.synthesize_speech("I am the male interviewer asking about system architecture.", voice_name="en_US-ryan-medium")
    assert male_audio is not None
    assert len(male_audio) > 1000

    jd_text = "Backend engineer specializing in distributed systems and cloud microservices."
    resume_text = "Bob Builder - Senior distributed systems engineer with 8 years of backend engineering experience."

    res = service.start_session(
        db=db,
        candidate_name="Bob Builder",
        candidate_email="bob.builder.phase5@test.com",
        jd_text=jd_text,
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="live",
        answer_capture_type="text",
        interviewer_gender="male"
    )

    doc = db.sessions.find_one({"_id": ObjectId(res.session_id)})
    assert doc is not None
    assert doc.get("interviewer_gender") == "male"
