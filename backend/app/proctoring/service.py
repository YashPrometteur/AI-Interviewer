"""Phase 3: Proctoring service managing telemetry event ingestion, frame analysis dispatch, and MongoDB persistence."""
import os
import base64
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from bson import ObjectId
from pymongo.database import Database
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.models import build_proctoring_event_entry
from app.proctoring.scoring import get_event_severity
from app.proctoring import vision

logger = logging.getLogger("ai_interviewer")


def parse_session_object_id(session_id: str) -> ObjectId:
    """Safely parses a string ID to MongoDB ObjectId."""
    try:
        return ObjectId(session_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid session ID format.")


def save_evidence_screenshot(session_id: str, event_type: str, image_bytes: bytes) -> str:
    """Saves evidence screenshot to uploads/evidence/ and returns relative URL."""
    evidence_dir = Path(settings.BACKEND_DIR) / "uploads" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{session_id}_{timestamp_str}_{event_type}.jpg"
    file_path = evidence_dir / filename
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    return f"uploads/evidence/{filename}"


def log_proctoring_event(
    db: Database,
    session_id: str,
    event_type: str,
    question_id: Optional[str] = None,
    details: Optional[str] = None,
    severity: Optional[str] = None,
    screenshot_base64: Optional[str] = None,
    screenshot_url: Optional[str] = None
) -> Dict[str, Any]:
    """Appends a proctoring telemetry event to the session document in MongoDB with optional evidence screenshot.
    
    Shared by both browser-native telemetry endpoint (tab-switch, focus, multi-screen)
    and periodic frame-sampling analysis (no_face_detected, multiple_faces_detected, analysis_error).
    """
    obj_id = parse_session_object_id(session_id)
    session = db.sessions.find_one({"_id": obj_id})
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found.")

    if session.get("status") in ["completed", "expired", "abandoned"]:
        # Don't fail if session is already closed, but don't log further active events
        return {"event_type": event_type, "severity": severity or "low", "timestamp": datetime.now(timezone.utc), "details": "Session is not active"}

    # Process base64 screenshot if provided
    final_screenshot_url = screenshot_url
    if screenshot_base64 and not final_screenshot_url:
        try:
            raw_b64 = screenshot_base64.split(",", 1)[1] if "," in screenshot_base64 else screenshot_base64
            img_bytes = base64.b64decode(raw_b64)
            if len(img_bytes) > 10:
                final_screenshot_url = save_evidence_screenshot(session_id, event_type, img_bytes)
        except Exception as e:
            logger.warning(f"[PROCTORING] Failed to decode base64 screenshot for '{event_type}': {e}")

    event_severity = severity or get_event_severity(event_type)
    now = datetime.now(timezone.utc)
    formatted_ts = now.strftime("%b %d, %Y, %I:%M:%S %p")

    event_entry = build_proctoring_event_entry(
        event_type=event_type,
        severity=event_severity,
        timestamp=now,
        question_id=question_id,
        details=details,
        screenshot_url=final_screenshot_url
    )
    event_entry["formatted_timestamp"] = formatted_ts

    db.sessions.update_one(
        {"_id": obj_id},
        {
            "$push": {"proctoring_events": event_entry},
            "$set": {"last_active_at": now}
        }
    )

    logger.info(f"[PROCTORING] Logged {event_severity.upper()} event '{event_type}' at {formatted_ts} for session {session_id} (Proof: {bool(final_screenshot_url)})")
    return event_entry


def process_proctoring_frame(
    db: Database,
    session_id: str,
    frame_bytes: bytes,
    question_id: Optional[str] = None
) -> Dict[str, Any]:
    """Processes a periodic camera frame snapshot:
    1. Runs two-pass detection (YOLOv8 person detection + OpenCV Haar face detection).
    2. Automatically logs proctoring anomaly events with photo proof if no face is detected or multiple people are present.
    3. Returns analysis result without interrupting interview flow.
    """
    analysis = vision.analyze_frame(frame_bytes)
    
    logged_event = None
    severity = None
    evidence_screenshot_url = None

    if not analysis.get("success"):
        # Log system analysis error as low severity for transparency
        logged_event = "analysis_error"
        severity = "low"
        log_proctoring_event(
            db=db,
            session_id=session_id,
            event_type=logged_event,
            question_id=question_id,
            details=f"Frame analysis failed: {analysis.get('error')}",
            severity=severity
        )
    else:
        person_count = analysis.get("person_count", 1)
        face_count = analysis.get("face_count", 1)
        phone_detected = analysis.get("phone_detected", False)
        phone_count = analysis.get("phone_count", 0)

        # 1. Highest Priority: Mobile phone / unauthorized electronic device detected
        if phone_detected:
            logged_event = "cell_phone_detected"
            severity = "high"
            try:
                evidence_screenshot_url = save_evidence_screenshot(session_id, logged_event, frame_bytes)
            except Exception as e:
                logger.warning(f"[PROCTORING] Failed to save cell phone proof image: {e}")

            log_proctoring_event(
                db=db,
                session_id=session_id,
                event_type=logged_event,
                question_id=question_id,
                details=f"Unauthorized mobile phone/device detected in camera frame ({phone_count} device{'s' if phone_count > 1 else ''})",
                severity=severity,
                screenshot_url=evidence_screenshot_url
            )
        elif (person_count is not None and person_count > 1) or (face_count is not None and face_count > 1):
            logged_event = "multiple_faces_detected"
            severity = "high"
            try:
                evidence_screenshot_url = save_evidence_screenshot(session_id, logged_event, frame_bytes)
            except Exception as e:
                logger.warning(f"[PROCTORING] Failed to save multiple faces proof image: {e}")

            log_proctoring_event(
                db=db,
                session_id=session_id,
                event_type=logged_event,
                question_id=question_id,
                details=f"Multiple individuals detected in frame (persons: {person_count}, faces: {face_count})",
                severity=severity,
                screenshot_url=evidence_screenshot_url
            )
        elif (face_count is not None and face_count == 0) or (person_count is not None and person_count == 0):
            logged_event = "no_face_detected"
            severity = "medium"
            try:
                evidence_screenshot_url = save_evidence_screenshot(session_id, logged_event, frame_bytes)
            except Exception as e:
                logger.warning(f"[PROCTORING] Failed to save out-of-frame proof image: {e}")

            log_proctoring_event(
                db=db,
                session_id=session_id,
                event_type=logged_event,
                question_id=question_id,
                details=f"No candidate face visible to camera (persons: {person_count}, faces: {face_count})",
                severity=severity,
                screenshot_url=evidence_screenshot_url
            )

    return {
        "person_count": analysis.get("person_count"),
        "face_count": analysis.get("face_count"),
        "phone_detected": analysis.get("phone_detected", False),
        "phone_count": analysis.get("phone_count", 0),
        "event_logged": logged_event,
        "severity": severity,
        "screenshot_url": evidence_screenshot_url,
        "success": analysis.get("success", False),
        "error": analysis.get("error")
    }
