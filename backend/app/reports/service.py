"""Phase 1: Report service for compiling complete evaluation scorecards, transcripts, and recommendations from MongoDB."""
from datetime import datetime, timezone
from bson import ObjectId
from pymongo.database import Database
from fastapi import HTTPException, status

from app.db.schemas import FullReportResponse, ReportOut, TranscriptItem, ProctoringEventOut

def get_full_report(db: Database, session_id: str) -> FullReportResponse:
    """Retrieves full evaluation report including candidate metadata, AI synthesis, and full turn transcript from MongoDB."""
    try:
        obj_id = ObjectId(session_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid session ID format.")

    session = db.sessions.find_one({"_id": obj_id})
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found.")

    cand = session.get("candidate", {})
    report = session.get("report")
    questions = sorted(session.get("questions", []), key=lambda q: q.get("order_index", 0))

    transcript_items = []
    for q in questions:
        ans = q.get("answer")
        transcript_items.append(TranscriptItem(
            question_id=q.get("question_id", ""),
            question_text=q.get("text", ""),
            skill_tag=q.get("skill_tag", ""),
            difficulty=q.get("difficulty", "medium"),
            is_followup=q.get("is_followup", False),
            parent_question_id=q.get("parent_question_id"),
            audio_url=q.get("audio_url"),
            avatar_video_url=q.get("avatar_video_url"),
            mouth_amplitude_track=q.get("mouth_amplitude_track"),
            answer_text=ans.get("answer_text") if ans else None,
            score=ans.get("score") if ans else None,
            reasoning=ans.get("reasoning") if ans else None,
            red_flag=ans.get("red_flag", False) if ans else False,
            eval_provider=ans.get("eval_provider", "mock") if ans else "mock",
            answer_source=ans.get("answer_source", "text") if ans else "text",
            recording_url=ans.get("recording_url") if ans else None,
            transcription_confidence=ans.get("transcription_confidence") if ans else None,
            transcription_mode=ans.get("transcription_mode") if ans else None
        ))

    report_out = None
    if report:
        report_out = ReportOut(
            id=str(session["_id"]),
            session_id=session_id,
            summary_text=report.get("summary_text", ""),
            strengths=report.get("strengths", []),
            weaknesses=report.get("weaknesses", []),
            recommendation=report.get("recommendation", "borderline"),
            eval_provider=report.get("eval_provider", "mock"),
            created_at=report.get("generated_at") or session.get("created_at") or datetime.now(timezone.utc)
        )

    proctoring_events_raw = session.get("proctoring_events", [])
    proctoring_events_out = []
    for pe in proctoring_events_raw:
        ts = pe.get("timestamp") or datetime.now(timezone.utc)
        fmt_ts = pe.get("formatted_timestamp") or ts.strftime("%b %d, %Y, %I:%M:%S %p")
        proctoring_events_out.append(
            ProctoringEventOut(
                event_type=pe.get("event_type", ""),
                severity=pe.get("severity", "low"),
                timestamp=ts,
                formatted_timestamp=fmt_ts,
                question_id=pe.get("question_id"),
                details=pe.get("details"),
                screenshot_url=pe.get("screenshot_url")
            )
        )

    return FullReportResponse(
        session_id=session_id,
        candidate_name=cand.get("name", "Unknown"),
        candidate_email=cand.get("email", "Unknown"),
        job_role="Position Candidate",
        status=session.get("status", "pending"),
        interview_mode=session.get("interview_mode", "live"),
        answer_capture_type=session.get("answer_capture_type", "text"),
        interviewer_photo_url=session.get("interviewer_photo_url"),
        session_deadline=session.get("session_deadline"),
        last_active_at=session.get("last_active_at"),
        overall_score=session.get("overall_score"),
        integrity_score=session.get("integrity_score"),
        integrity_flags=session.get("integrity_flags", []),
        proctoring_events=proctoring_events_out,
        session_video_url=session.get("session_video_url"),
        eval_provider=report.get("eval_provider", "mock") if report else "mock",
        created_at=session.get("created_at") or datetime.now(timezone.utc),
        completed_at=session.get("completed_at"),
        report=report_out,
        transcript=transcript_items
    )
