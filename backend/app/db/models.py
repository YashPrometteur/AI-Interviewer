"""Phase 1: MongoDB document structure helpers and builders.
Defines the canonical single-collection embedded document structure for interview sessions.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union

def generate_uuid() -> str:
    """Generates a unique string identifier for questions and embedded records."""
    return str(uuid.uuid4())

def build_candidate_entry(name: str, email: str, resume_text: str) -> Dict[str, Any]:
    """Builds embedded candidate information."""
    return {
        "name": name.strip(),
        "email": email.strip(),
        "resume_text": resume_text.strip()
    }

def build_question_entry(
    text: str,
    skill_tag: str,
    difficulty: str,
    order_index: Union[int, float],
    question_id: Optional[str] = None,
    is_followup: bool = False,
    parent_question_id: Optional[str] = None,
    audio_url: Optional[str] = None,
    avatar_video_url: Optional[str] = None,
    mouth_amplitude_track: Optional[List[float]] = None
) -> Dict[str, Any]:
    """Builds an embedded question entry with initial null answer and optional TTS audio / avatar video / follow-up metadata."""
    return {
        "question_id": question_id or generate_uuid(),
        "text": text.strip(),
        "skill_tag": skill_tag.strip(),
        "difficulty": difficulty.lower().strip(),
        "order_index": order_index,
        "is_followup": bool(is_followup),
        "parent_question_id": parent_question_id,
        "audio_url": audio_url,
        "avatar_video_url": avatar_video_url,
        "mouth_amplitude_track": mouth_amplitude_track,
        "answer": None
    }

def build_answer_entry(
    answer_text: str,
    score: float,
    reasoning: str,
    red_flag: bool = False,
    eval_provider: str = "mock",
    answer_source: str = "text",
    recording_url: Optional[str] = None,
    transcription_confidence: Optional[float] = None,
    transcription_mode: Optional[str] = None,
    needs_followup: bool = False,
    followup_question: Optional[str] = None,
    followup_reason: Optional[str] = None,
    answered_at: Optional[datetime] = None
) -> Dict[str, Any]:
    """Builds an embedded answer object with Phase 2 media tracking and Phase 4 follow-up decisions."""
    return {
        "answer_text": answer_text.strip(),
        "score": round(float(score), 2),
        "reasoning": reasoning.strip(),
        "red_flag": bool(red_flag),
        "eval_provider": eval_provider,
        "answer_source": (answer_source or "text").lower().strip(),  # text, video, audio
        "recording_url": recording_url,
        "transcription_confidence": round(float(transcription_confidence), 3) if transcription_confidence is not None else None,
        "transcription_mode": transcription_mode,  # "real", "fallback", or None for text
        "needs_followup": bool(needs_followup),
        "followup_question": followup_question.strip() if followup_question else None,
        "followup_reason": followup_reason.strip() if followup_reason else None,
        "answered_at": answered_at or datetime.now(timezone.utc)
    }

def build_report_entry(
    summary_text: str,
    strengths: List[str],
    weaknesses: List[str],
    recommendation: str,
    eval_provider: str = "mock",
    generated_at: Optional[datetime] = None
) -> Dict[str, Any]:
    """Builds an embedded executive report object."""
    return {
        "summary_text": summary_text.strip(),
        "strengths": list(strengths),
        "weaknesses": list(weaknesses),
        "recommendation": recommendation.lower().strip(),
        "eval_provider": eval_provider,
        "generated_at": generated_at or datetime.now(timezone.utc)
    }

def build_proctoring_event_entry(
    event_type: str,
    severity: str = "low",
    timestamp: Optional[datetime] = None,
    question_id: Optional[str] = None,
    details: Optional[str] = None,
    screenshot_url: Optional[str] = None
) -> Dict[str, Any]:
    """Builds an embedded proctoring event entry for integrity tracking with optional visual proof screenshot."""
    return {
        "event_type": event_type.strip(),
        "severity": (severity or "low").lower().strip(),  # low, medium, high
        "timestamp": timestamp or datetime.now(timezone.utc),
        "question_id": question_id,
        "details": details.strip() if details else None,
        "screenshot_url": screenshot_url
    }


def build_session_document(
    candidate_name: str,
    candidate_email: str,
    resume_text: str,
    jd_text: str,
    skill_weights: Optional[Dict[str, float]] = None,
    questions: Optional[List[Dict[str, Any]]] = None,
    status: str = "in_progress",
    interview_mode: str = "live",
    answer_capture_type: str = "text",
    session_deadline: Optional[datetime] = None,
    interviewer_photo_url: Optional[str] = None,
    interviewer_gender: Optional[str] = None
) -> Dict[str, Any]:
    """Builds a complete, canonical Session MongoDB document with embedded candidate, questions, avatar, and lifecycle metadata."""
    now = datetime.now(timezone.utc)
    return {
        "candidate": build_candidate_entry(candidate_name, candidate_email, resume_text),
        "jd_text": jd_text.strip(),
        "status": status,  # pending, in_progress, completed, expired, abandoned
        "interview_mode": (interview_mode or "live").lower().strip(),  # live, async
        "answer_capture_type": (answer_capture_type or "text").lower().strip(),  # text, video
        "session_deadline": session_deadline,
        "interviewer_photo_url": interviewer_photo_url,
        "interviewer_gender": interviewer_gender,
        "last_active_at": now,
        "skill_weights": skill_weights or {},
        "questions": questions or [],
        "overall_score": None,
        "report": None,
        "proctoring_events": [],
        "integrity_score": None,
        "integrity_flags": [],
        "session_video_url": None,
        "created_at": now,
        "completed_at": None
    }
