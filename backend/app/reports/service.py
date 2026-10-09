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


def generate_printable_html_report(db: Database, session_id: str) -> str:
    """Generates a standalone, beautifully formatted printable HTML evaluation report."""
    data = get_full_report(db, session_id)
    cand_name = data.candidate_name
    cand_email = data.candidate_email
    score = f"{data.overall_score:.1f}" if data.overall_score is not None else "N/A"
    integrity = f"{data.integrity_score:.1f}" if data.integrity_score is not None else "10.0"
    rec = data.report.recommendation.upper() if data.report else "PENDING"
    summary = data.report.summary_text if data.report else "Interview evaluation in progress."
    strengths = "".join(f"<li>{s}</li>" for s in (data.report.strengths if data.report else []))
    weaknesses = "".join(f"<li>{w}</li>" for w in (data.report.weaknesses if data.report else []))

    transcript_rows = ""
    for idx, item in enumerate(data.transcript, 1):
        q_score = f"{item.score:.1f}/10" if item.score is not None else "Pending"
        transcript_rows += f"""
        <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #e2e8f0; border-radius: 8px; background: #fafafa;">
            <div style="font-weight: bold; color: #1e293b; margin-bottom: 5px;">Question {idx} ({item.skill_tag} • {item.difficulty}):</div>
            <div style="color: #334155; margin-bottom: 10px;">{item.question_text}</div>
            <div style="background: #fff; padding: 10px; border-left: 3px solid #3b82f6; margin-bottom: 8px; font-size: 0.9em;">
                <strong>Candidate Answer:</strong> {item.answer_text or 'No response recorded.'}
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 0.85em; color: #64748b;">
                <span><strong>AI Score:</strong> {q_score}</span>
                <span><strong>Feedback:</strong> {item.reasoning or 'N/A'}</span>
            </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Interview Scorecard - {cand_name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #0f172a; max-width: 800px; margin: 0 auto; padding: 30px 20px; }}
        .header {{ border-bottom: 2px solid #0f172a; padding-bottom: 15px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-end; }}
        .badge {{ padding: 6px 12px; border-radius: 6px; font-weight: bold; display: inline-block; }}
        .score {{ font-size: 24px; font-weight: 800; color: #2563eb; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; }}
        h1, h2, h3 {{ margin-top: 0; }}
        ul {{ margin: 0; padding-left: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Candidate Evaluation Scorecard</h1>
            <div><strong>Candidate:</strong> {cand_name} ({cand_email})</div>
            <div><strong>Session ID:</strong> {session_id}</div>
        </div>
        <div style="text-align: right;">
            <div class="score">{score} / 10</div>
            <div>Recommendation: <strong>{rec}</strong></div>
            <div>Integrity Score: <strong>{integrity} / 10</strong></div>
        </div>
    </div>

    <div class="card" style="margin-bottom: 20px;">
        <h2>Executive AI Summary</h2>
        <p>{summary}</p>
    </div>

    <div class="grid">
        <div class="card" style="border-top: 4px solid #10b981;">
            <h3>Key Strengths</h3>
            <ul>{strengths or '<li>None specified</li>'}</ul>
        </div>
        <div class="card" style="border-top: 4px solid #ef4444;">
            <h3>Areas for Growth</h3>
            <ul>{weaknesses or '<li>None specified</li>'}</ul>
        </div>
    </div>

    <h2>Technical Turn Transcript & Question Evaluations</h2>
    {transcript_rows}

    <div style="text-align: center; margin-top: 30px; font-size: 0.8em; color: #94a3b8;">
        Generated by AI Interviewer Platform • Verified Evaluation Record
    </div>
</body>
</html>"""

