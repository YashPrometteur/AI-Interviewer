"""Phase 2: Interview service managing session lifecycle, adaptive question flow, audio/video answer submission, and async/live state machines in MongoDB."""
import uuid
import time
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import cv2
from bson import ObjectId
from pymongo.database import Database
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.models import (
    build_session_document, build_question_entry, build_answer_entry, build_report_entry
)
from app.db.schemas import (
    SessionCreateResponse, SessionListItem, QuestionOut,
    NextQuestionResponse, AnswerEvaluationOut, CompleteSessionResponse, ReportOut
)
from app.interview.parser import parse_resume, extract_skills_from_jd, extract_candidate_background
from app.interview import media, tts, avatar
from app.ai.chains import generate_questions, evaluate_answer, generate_summary
from app.ai.scoring import compute_weighted_score, determine_difficulty_progression

logger = logging.getLogger("ai_interviewer")

def parse_object_id(id_str: str) -> ObjectId:
    """Helper to safely parse string to MongoDB ObjectId."""
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid session ID format.")


def check_session_validity(db: Database, session: Dict[str, Any]) -> None:
    """Validates session lifecycle state:
    - If completed, expired, or abandoned: blocks further turns.
    - If async mode and past session_deadline: marks expired in MongoDB and raises HTTPException(403).
    - If live mode and inactive for > LIVE_SESSION_TIMEOUT_MINUTES: marks abandoned in MongoDB and raises HTTPException(403).
    """
    current_status = session.get("status", "pending")
    session_id = session["_id"]
    now = datetime.now(timezone.utc)

    if current_status == "completed":
        return

    if current_status == "expired":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This async interview session has expired as the submission deadline has passed."
        )

    if current_status == "abandoned":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This live interview session was abandoned due to prolonged inactivity."
        )

    # 1. Check Async Deadline Expiry
    mode = session.get("interview_mode", "live")
    deadline = session.get("session_deadline")
    if mode == "async" and deadline:
        # Normalize deadline to timezone-aware UTC datetime
        if isinstance(deadline, datetime) and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now > deadline:
            db.sessions.update_one(
                {"_id": session_id},
                {"$set": {"status": "expired", "completed_at": now}}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This async interview session has expired as the submission deadline has passed."
            )

    # 2. Check Live Session Inactivity Abandonment
    if mode == "live" and current_status in ["pending", "in_progress"]:
        last_active = session.get("last_active_at") or session.get("created_at")
        if last_active:
            if isinstance(last_active, datetime) and last_active.tzinfo is None:
                last_active = last_active.replace(tzinfo=timezone.utc)
            inactivity_seconds = (now - last_active).total_seconds()
            max_inactivity_seconds = settings.LIVE_SESSION_TIMEOUT_MINUTES * 60
            if inactivity_seconds > max_inactivity_seconds:
                db.sessions.update_one(
                    {"_id": session_id},
                    {"$set": {"status": "abandoned", "completed_at": now}}
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This live interview session has been marked as abandoned due to {int(inactivity_seconds // 60)} minutes of inactivity."
                )


def prune_old_sessions_if_needed(db: Database) -> int:
    """Auto-prunes the oldest 10 sessions when the database reaches or exceeds 50 entries.
    Keeps the latest 40-50 interviews and cleans up associated recording files.
    """
    try:
        total_count = db.sessions.count_documents({})
        if total_count >= 50:
            oldest_docs = list(db.sessions.find({}, {"_id": 1}).sort("created_at", 1).limit(10))
            if oldest_docs:
                oldest_ids = [doc["_id"] for doc in oldest_docs]
                recordings_dir = Path(settings.RECORDINGS_DIR)
                if recordings_dir.exists():
                    for doc in oldest_docs:
                        sid_str = str(doc["_id"])
                        for fpath in recordings_dir.glob(f"*{sid_str}*"):
                            try:
                                fpath.unlink(missing_ok=True)
                            except Exception as e:
                                logger.warning(f"[PRUNING] Could not delete old recording file {fpath}: {e}")

                del_res = db.sessions.delete_many({"_id": {"$in": oldest_ids}})
                logger.info(f"[PRUNING] Auto-pruned {del_res.deleted_count} oldest sessions (total was {total_count}).")
                return del_res.deleted_count
    except Exception as e:
        logger.warning(f"[PRUNING] Auto-prune encountered an error: {e}")
    return 0


def start_session(
    db: Database,
    candidate_name: str,
    candidate_email: str,
    jd_text: str,
    resume_bytes: bytes,
    resume_filename: str,
    interview_mode: str = "live",
    answer_capture_type: str = "text",
    interviewer_photo_bytes: Optional[bytes] = None,
    interviewer_photo_filename: Optional[str] = None,
    interviewer_gender: Optional[str] = "auto"
) -> SessionCreateResponse:
    """Validates inputs, extracts skills & background, generates question bank upfront, sets deadline if async,
    pre-synthesizes TTS audio and optional Wav2Lip lip-sync avatar videos, and persists session to MongoDB.
    """
    # 0. Enforce database capacity management (prunes oldest 10 when count >= 50)
    prune_old_sessions_if_needed(db)

    # 1. Edge Case Validation: Check minimum text lengths
    if not candidate_name or len(candidate_name.strip()) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Candidate name is required.")
    
    if not candidate_email or "@" not in candidate_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid candidate email is required.")

    if not jd_text or len(jd_text.strip()) < settings.MIN_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job description is too short ({len(jd_text.strip())} chars). Please provide at least {settings.MIN_TEXT_LENGTH} characters of JD text."
        )

    # 2. Extract and validate resume text
    resume_text = parse_resume(resume_bytes, resume_filename)
    if not resume_text or len(resume_text.strip()) < settings.MIN_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded resume content is too short or could not be parsed ({len(resume_text.strip())} chars). Please upload a valid resume."
        )

    # 3. Upfront Interviewer Avatar Photo Validation & Gender Determination
    session_obj_id = ObjectId()
    session_id_str = str(session_obj_id)
    interviewer_photo_url = None
    photo_file_path = None
    effective_gender = interviewer_gender if interviewer_gender in ("male", "female") else None

    if interviewer_photo_bytes and len(interviewer_photo_bytes) > 0:
        # Validate that image is valid and has a single clear front-facing face
        validated_img, face_bbox = avatar.validate_interviewer_photo(interviewer_photo_bytes)
        photo_dir = Path(settings.INTERVIEWER_PHOTOS_DIR)
        photo_dir.mkdir(parents=True, exist_ok=True)
        photo_file_path = photo_dir / f"{session_id_str}.jpg"
        cv2.imwrite(str(photo_file_path), validated_img)
        interviewer_photo_url = f"/sessions/{session_id_str}/interviewer-photo"
        logger.info(f"[AVATAR] Saved validated interviewer photo to: {photo_file_path}")

        if not effective_gender or effective_gender == "auto":
            effective_gender = avatar.detect_gender_from_photo(validated_img, face_bbox)
            logger.info(f"[AVATAR] Auto-detected interviewer photo gender: '{effective_gender}'")

    if not effective_gender or effective_gender == "auto":
        effective_gender = "female"

    interviewer_voice_name = "en_US-ryan-medium" if effective_gender == "male" else "en_US-lessac-medium"
    logger.info(f"[TTS] Interviewer persona gender: '{effective_gender}', voice model: '{interviewer_voice_name}'")

    # 4. AI Chain: Extract skills and candidate background (via Ollama qwen2.5:7b)
    skills_result = extract_skills_from_jd(jd_text)
    jd_skills = skills_result.get("skills", [])
    is_mock = skills_result.get("mock", False)

    bg_result = extract_candidate_background(resume_text, jd_skills)
    resume_summary = bg_result.get("background", {})
    is_mock = is_mock or bg_result.get("mock", False)

    # 5. AI Chain: Generate full question bank via Ollama
    q_result = generate_questions(jd_skills, resume_summary)
    generated_q_list = q_result.get("questions", [])
    is_mock = is_mock or q_result.get("mock", False)

    if not generated_q_list:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate interview questions.")

    # 6. Build Embedded Question List with pre-synthesized TTS audio & optional Wav2Lip Avatar Videos
    embedded_questions = []
    avatar_render_start = time.perf_counter()

    for idx, q_data in enumerate(generated_q_list):
        q_id = str(uuid.uuid4())
        q_text = q_data.get("text", "Technical question")
        audio_url = None
        avatar_video_url = None

        # Pre-synthesize Piper TTS audio with gender-matching voice model
        try:
            tts.synthesize_and_save_question_audio(session_id_str, q_id, q_text, voice_name=interviewer_voice_name)
            audio_url = f"/sessions/{session_id_str}/questions/{q_id}/audio"
        except Exception as e:
            logger.warning(f"[TTS] Pre-synthesis failed for question {q_id}: {e}")

        # Pre-render avatar MP4 (D-ID premium or local Wav2Lip) if interviewer avatar photo exists
        if interviewer_photo_url and photo_file_path and photo_file_path.exists():
            try:
                avatar_dir = Path(settings.AVATAR_VIDEOS_DIR)
                avatar_dir.mkdir(parents=True, exist_ok=True)
                video_target_path = avatar_dir / f"{session_id_str}_{q_id}.mp4"

                if settings.AVATAR_PROVIDER == "did" and settings.D_ID_API_KEY:
                    try:
                        avatar.render_did_video(
                            photo_path=str(photo_file_path),
                            text=q_text,
                            gender=effective_gender,
                            output_path=str(video_target_path)
                        )
                        avatar_video_url = f"/sessions/{session_id_str}/questions/{q_id}/avatar-video"
                    except Exception as did_err:
                        logger.warning(f"[D-ID] Premium render failed ({did_err}), falling back to local engine...")
                        audio_path = tts.get_question_audio_path(session_id_str, q_id)
                        if audio_path and audio_path.exists():
                            avatar.render_lipsync_video(str(photo_file_path), str(audio_path), output_path=str(video_target_path))
                            avatar_video_url = f"/sessions/{session_id_str}/questions/{q_id}/avatar-video"
                else:
                    audio_path = tts.get_question_audio_path(session_id_str, q_id)
                    if audio_path and audio_path.exists():
                        avatar.render_lipsync_video(str(photo_file_path), str(audio_path), output_path=str(video_target_path))
                        avatar_video_url = f"/sessions/{session_id_str}/questions/{q_id}/avatar-video"
            except Exception as e:
                logger.warning(f"[AVATAR] Lip-sync video pre-rendering failed for Q:{q_id}: {e}")

        q_entry = build_question_entry(
            text=q_text,
            skill_tag=q_data.get("skill_tag", "General"),
            difficulty=q_data.get("difficulty", "medium"),
            order_index=idx,
            question_id=q_id,
            is_followup=False,
            parent_question_id=None,
            audio_url=audio_url,
            avatar_video_url=avatar_video_url,
            mouth_amplitude_track=None
        )
        embedded_questions.append(q_entry)

    if interviewer_photo_url:
        total_avatar_time = time.perf_counter() - avatar_render_start
        logger.info(f"[AVATAR] Pre-rendering lip-sync for {len(embedded_questions)} questions took {total_avatar_time:.2f}s total.")

    # 7. Calculate deadline if async mode
    now = datetime.now(timezone.utc)
    norm_mode = "async" if (interview_mode or "").lower().strip() == "async" else "live"
    norm_capture = "video" if (answer_capture_type or "").lower().strip() == "video" else "text"
    session_deadline = now + timedelta(days=settings.ASYNC_SESSION_DEADLINE_DAYS) if norm_mode == "async" else None

    # 8. Build and Insert Session Document into MongoDB
    session_doc = build_session_document(
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        resume_text=resume_text,
        jd_text=jd_text,
        skill_weights=skills_result.get("skill_weights", {}),
        questions=embedded_questions,
        status="pending",
        interview_mode=norm_mode,
        answer_capture_type=norm_capture,
        session_deadline=session_deadline,
        interviewer_photo_url=interviewer_photo_url,
        interviewer_gender=effective_gender
    )
    session_doc["_id"] = session_obj_id
    db.sessions.insert_one(session_doc)

    return SessionCreateResponse(
        session_id=session_id_str,
        candidate_id=session_id_str,
        candidate_name=candidate_name.strip(),
        total_questions=len(embedded_questions),
        session_url=f"/interview?session_id={session_id_str}",
        interview_mode=norm_mode,
        answer_capture_type=norm_capture,
        session_deadline=session_deadline,
        interviewer_photo_url=interviewer_photo_url,
        mock=is_mock
    )


def get_next_question(db: Database, session_id: str, exclude_question_id: Optional[str] = None) -> NextQuestionResponse:
    """Returns the next unanswered question using adaptive difficulty progression, validating session expiry/activity."""
    obj_id = parse_object_id(session_id)
    session = db.sessions.find_one({"_id": obj_id})
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found.")

    # Validate session lifecycle (expiry / timeout)
    check_session_validity(db, session)

    now = datetime.now(timezone.utc)
    update_fields = {"last_active_at": now}
    if session.get("status") == "pending":
        update_fields["status"] = "in_progress"

    db.sessions.update_one({"_id": obj_id}, {"$set": update_fields})

    all_questions = session.get("questions", [])
    # Filter out already answered questions and any explicitly excluded question ID (prevent race conditions)
    unanswered_questions = [
        q for q in all_questions
        if q.get("answer") is None and (not exclude_question_id or q.get("question_id") != exclude_question_id)
    ]

    if not unanswered_questions:
        return NextQuestionResponse(
            question=None,
            remaining_count=0,
            is_completed=True,
            message="All questions completed. Ready to generate report.",
            interview_mode=session.get("interview_mode", "live"),
            answer_capture_type=session.get("answer_capture_type", "text"),
            session_deadline=session.get("session_deadline")
        )

    # Sort unanswered questions by order_index for progressive difficulty flow
    unanswered_questions = sorted(unanswered_questions, key=lambda q: q.get("order_index", 0))

    # Find answered questions ordered by answer timestamp safely with timezone awareness
    answered_questions = [q for q in all_questions if q.get("answer") is not None]

    if not answered_questions:
        # First question starts with lowest order index (usually Easy)
        chosen_question = unanswered_questions[0]
    else:
        def get_ans_ts(x):
            ans = x.get("answer") or {}
            ts = ans.get("answered_at")
            if not ts:
                return datetime.min.replace(tzinfo=timezone.utc)
            if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts

        sorted_answered = sorted(answered_questions, key=get_ans_ts, reverse=True)
        last_q = sorted_answered[0]

        # Check if the most recently answered question has a pending unanswered follow-up
        pending_followup = next(
            (q for q in unanswered_questions if q.get("is_followup") and q.get("parent_question_id") == last_q.get("question_id")),
            None
        )

        if pending_followup:
            chosen_question = pending_followup
        else:
            last_score = last_q["answer"].get("score", 5.0)
            last_diff = last_q.get("difficulty", "medium")
            target_difficulty = determine_difficulty_progression(last_score, last_diff)

            chosen_question = next(
                (q for q in unanswered_questions if (q.get("difficulty") or "").lower() == target_difficulty),
                unanswered_questions[0]
            )

    q_out = QuestionOut(
        id=chosen_question["question_id"],
        session_id=session_id,
        text=chosen_question["text"],
        skill_tag=chosen_question["skill_tag"],
        difficulty=chosen_question["difficulty"],
        order_index=chosen_question["order_index"],
        is_followup=chosen_question.get("is_followup", False),
        parent_question_id=chosen_question.get("parent_question_id"),
        audio_url=chosen_question.get("audio_url"),
        avatar_video_url=chosen_question.get("avatar_video_url"),
        mouth_amplitude_track=chosen_question.get("mouth_amplitude_track"),
        interviewer_photo_url=session.get("interviewer_photo_url")
    )

    return NextQuestionResponse(
        question=q_out,
        remaining_count=len(unanswered_questions),
        is_completed=False,
        interview_mode=session.get("interview_mode", "live"),
        answer_capture_type=session.get("answer_capture_type", "text"),
        session_deadline=session.get("session_deadline"),
        interviewer_photo_url=session.get("interviewer_photo_url")
    )


def submit_answer(
    db: Database,
    session_id: str,
    question_id: str,
    answer_text: str,
    answer_source: str = "text",
    recording_url: Optional[str] = None,
    transcription_confidence: Optional[float] = None,
    transcription_mode: Optional[str] = None
) -> AnswerEvaluationOut:
    """Evaluates candidate response via Fallback Chain (Groq -> Ollama -> Mock), tags tier & media metadata, embeds Answer in MongoDB, and triggers dynamic follow-up if warranted."""
    cleaned_answer = (answer_text or "").strip()
    if not cleaned_answer or len(cleaned_answer) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answer text cannot be empty or whitespace-only. Please submit a valid technical response."
        )

    obj_id = parse_object_id(session_id)
    session = db.sessions.find_one({"_id": obj_id})
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found.")

    # Validate session lifecycle (expiry / timeout)
    check_session_validity(db, session)

    # Find matching question in embedded questions array
    target_q = None
    for q in session.get("questions", []):
        if q.get("question_id") == question_id:
            target_q = q
            break

    if not target_q:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found in this session.")

    if target_q.get("answer") is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This question has already been answered.")

    # AI Chain Evaluation with Single-Call Evaluation + Dynamic Follow-Up Decision
    is_transcribed = answer_source in ("video", "audio") or (transcription_mode is not None)
    eval_result = evaluate_answer(
        question=target_q["text"],
        skill_tag=target_q["skill_tag"],
        answer_text=cleaned_answer,
        is_transcribed=is_transcribed
    )

    eval_provider = eval_result.get("eval_provider", "mock")
    now = datetime.now(timezone.utc)

    answer_entry = build_answer_entry(
        answer_text=cleaned_answer,
        score=eval_result["score"],
        reasoning=eval_result["reasoning"],
        red_flag=eval_result.get("red_flag", False),
        eval_provider=eval_provider,
        answer_source=answer_source,
        recording_url=recording_url,
        transcription_confidence=transcription_confidence,
        transcription_mode=transcription_mode,
        needs_followup=eval_result.get("needs_followup", False),
        followup_question=eval_result.get("followup_question"),
        followup_reason=eval_result.get("followup_reason"),
        answered_at=now
    )

    # Atomically update the embedded question's answer and update last_active_at
    db.sessions.update_one(
        {"_id": obj_id, "questions.question_id": question_id},
        {"$set": {
            "questions.$.answer": answer_entry,
            "last_active_at": now
        }}
    )

    # Dynamic Counter-Question Generation: Check depth cap (MAX_FOLLOWUPS_PER_QUESTION = 1)
    # A follow-up question cannot itself spawn another follow-up
    if (
        not target_q.get("is_followup")
        and eval_result.get("needs_followup")
        and eval_result.get("followup_question")
    ):
        existing_followups = [
            q for q in session.get("questions", [])
            if q.get("parent_question_id") == question_id
        ]
        if len(existing_followups) < settings.MAX_FOLLOWUPS_PER_QUESTION:
            fq_text = eval_result["followup_question"].strip()
            fq_id = str(uuid.uuid4())
            fq_audio_url = None
            fq_mouth_track = None
            try:
                followup_gender = session.get("interviewer_gender", "female")
                followup_voice = "en_US-ryan-medium" if followup_gender == "male" else "en_US-lessac-medium"
                tts.synthesize_and_save_question_audio(session_id, fq_id, fq_text, voice_name=followup_voice)
                fq_audio_url = f"/sessions/{session_id}/questions/{fq_id}/audio"

                # Lightweight real-time amplitude track extraction for live follow-up avatar animation
                fq_audio_path = tts.get_question_audio_path(session_id, fq_id)
                if fq_audio_path and fq_audio_path.exists():
                    with open(fq_audio_path, "rb") as f:
                        fq_bytes = f.read()
                    fq_mouth_track = avatar.extract_mouth_amplitude_track(fq_bytes)
            except Exception as e:
                logger.warning(f"[TTS/AVATAR] Follow-up audio/amplitude synthesis failed for Q:{fq_id}: {e}")

            followup_q_entry = build_question_entry(
                text=fq_text,
                skill_tag=target_q.get("skill_tag", "General"),
                difficulty=target_q.get("difficulty", "medium"),
                order_index=float(target_q.get("order_index", 0)) + 0.1,
                question_id=fq_id,
                is_followup=True,
                parent_question_id=question_id,
                audio_url=fq_audio_url,
                avatar_video_url=None,
                mouth_amplitude_track=fq_mouth_track
            )
            db.sessions.update_one(
                {"_id": obj_id},
                {"$push": {"questions": followup_q_entry}}
            )
            logger.info(f"[FOLLOW-UP] Generated and inserted follow-up question for parent {question_id}: '{fq_text[:60]}...'")

    return AnswerEvaluationOut(
        answer_id=question_id,
        question_id=question_id,
        score=answer_entry["score"],
        reasoning=answer_entry["reasoning"],
        red_flag=answer_entry["red_flag"],
        needs_followup=eval_result.get("needs_followup", False),
        followup_question=eval_result.get("followup_question"),
        followup_reason=eval_result.get("followup_reason"),
        eval_provider=eval_provider,
        answer_source=answer_source,
        recording_url=recording_url,
        transcription_confidence=transcription_confidence,
        transcription_mode=transcription_mode,
        mock=eval_result.get("mock", False)
    )


def complete_session(db: Database, session_id: str) -> CompleteSessionResponse:
    """Aggregates all question evaluations, computes weighted score, generates report with tier tagging in MongoDB."""
    obj_id = parse_object_id(session_id)
    session = db.sessions.find_one({"_id": obj_id})
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found.")

    # Check if report already generated
    existing_report = session.get("report")
    if existing_report and session.get("status") == "completed":
        rep_out = ReportOut(
            id=str(session["_id"]),
            session_id=session_id,
            summary_text=existing_report["summary_text"],
            strengths=existing_report.get("strengths", []),
            weaknesses=existing_report.get("weaknesses", []),
            recommendation=existing_report.get("recommendation", "borderline"),
            eval_provider=existing_report.get("eval_provider", "mock"),
            created_at=existing_report.get("generated_at") or session.get("created_at") or datetime.now(timezone.utc)
        )
        return CompleteSessionResponse(
            session_id=session_id,
            status="completed",
            overall_score=session.get("overall_score", 0.0),
            eval_provider=existing_report.get("eval_provider", "mock"),
            report=rep_out
        )

    # Collect answers and questions from embedded array
    questions = sorted(session.get("questions", []), key=lambda q: q.get("order_index", 0))
    unanswered = [q for q in questions if q.get("answer") is None]
    if unanswered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete session: {len(unanswered)} question(s) remain unanswered ({len(questions) - len(unanswered)}/{len(questions)} completed). All interview questions must be answered before generating the final report."
        )

    transcript_items = []
    answers_data = []

    for q in questions:
        ans = q.get("answer")
        if ans:
            answers_data.append({
                "skill_tag": q["skill_tag"],
                "score": ans["score"],
                "difficulty": q["difficulty"]
            })
            transcript_items.append({
                "question": q["text"],
                "skill_tag": q["skill_tag"],
                "difficulty": q["difficulty"],
                "answer": ans["answer_text"],
                "score": ans["score"],
                "reasoning": ans["reasoning"],
                "red_flag": ans["red_flag"],
                "eval_provider": ans.get("eval_provider", "mock")
            })

    # Compute weighted score
    skill_weights = session.get("skill_weights", [])
    overall_score = compute_weighted_score(answers_data, skill_weights)

    # Compute Candidate Integrity Score & Flags from Proctoring Events
    from app.proctoring.scoring import compute_integrity_score, generate_integrity_flags
    proctoring_events = session.get("proctoring_events", [])
    integrity_score = compute_integrity_score(proctoring_events)
    integrity_flags = generate_integrity_flags(proctoring_events)

    # Generate Summary via AI chain with Fallback Chain
    candidate_name = session.get("candidate", {}).get("name", "Candidate")
    summary_result = generate_summary({
        "candidate_name": candidate_name,
        "overall_score": overall_score,
        "transcript": transcript_items,
        "integrity_flags": integrity_flags
    })

    eval_provider = summary_result.get("eval_provider", "mock")

    now = datetime.now(timezone.utc)
    report_entry = build_report_entry(
        summary_text=summary_result["summary"],
        strengths=summary_result.get("strengths", []),
        weaknesses=summary_result.get("weaknesses", []),
        recommendation=summary_result.get("recommendation", "borderline"),
        eval_provider=eval_provider,
        generated_at=now
    )

    db.sessions.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "completed",
            "overall_score": overall_score,
            "integrity_score": integrity_score,
            "integrity_flags": integrity_flags,
            "report": report_entry,
            "completed_at": now,
            "last_active_at": now
        }}
    )

    rep_out = ReportOut(
        id=str(session["_id"]),
        session_id=session_id,
        summary_text=report_entry["summary_text"],
        strengths=report_entry["strengths"],
        weaknesses=report_entry["weaknesses"],
        recommendation=report_entry["recommendation"],
        eval_provider=eval_provider,
        created_at=now,
        mock=summary_result.get("mock", False)
    )

    return CompleteSessionResponse(
        session_id=session_id,
        status="completed",
        overall_score=overall_score,
        integrity_score=integrity_score,
        integrity_flags=integrity_flags,
        eval_provider=eval_provider,
        report=rep_out,
        mock=summary_result.get("mock", False)
    )


def list_sessions(db: Database) -> List[SessionListItem]:
    """Retrieves all interview sessions for recruiter dashboard view (optimized projection)."""
    cursor = db.sessions.find(
        {},
        projection={"jd_text": 0, "candidate.resume_text": 0}
    ).sort("created_at", -1)

    results = []
    for s in cursor:
        s_id = str(s["_id"])
        cand = s.get("candidate", {})
        questions = s.get("questions", [])
        total_q = len(questions)
        answered_q = sum(1 for q in questions if q.get("answer") is not None)

        results.append(SessionListItem(
            id=s_id,
            candidate_id=s_id,
            candidate_name=cand.get("name", "Unknown"),
            candidate_email=cand.get("email", "Unknown"),
            status=s.get("status", "pending"),
            interview_mode=s.get("interview_mode", "live"),
            answer_capture_type=s.get("answer_capture_type", "text"),
            session_deadline=s.get("session_deadline"),
            interviewer_photo_url=s.get("interviewer_photo_url"),
            last_active_at=s.get("last_active_at"),
            overall_score=s.get("overall_score"),
            integrity_score=s.get("integrity_score"),
            created_at=s.get("created_at") or datetime.now(timezone.utc),
            completed_at=s.get("completed_at"),
            total_questions=total_q,
            answered_questions=answered_q
        ))
    return results


def save_session_video(db: Database, session_id: str, video_bytes: bytes, filename: Optional[str] = None) -> str:
    """Saves full session continuous video recording, injects seekable Cues/Duration index, and updates session document."""
    obj_id = parse_object_id(session_id)
    ext = Path(filename).suffix.lower() if filename else ".webm"
    if ext not in [".webm", ".mp4", ".m4a", ".mkv"]:
        ext = ".webm"
    video_dir = Path(settings.RECORDINGS_DIR)
    video_dir.mkdir(parents=True, exist_ok=True)
    video_filename = f"session_full_{session_id}{ext}"
    video_path = video_dir / video_filename
    with open(video_path, "wb") as f:
        f.write(video_bytes)

    # Ingest EBML Duration & Cues index so timeline scrubber is 100% seekable in VLC and web players
    try:
        media.remux_video_with_cues(video_path)
    except Exception as e:
        logger.warning(f"[MEDIA] Failed to remux video with cues: {e}")

    relative_url = f"uploads/recordings/{video_filename}"
    now = datetime.now(timezone.utc)
    db.sessions.update_one(
        {"_id": obj_id},
        {"$set": {"session_video_url": relative_url, "last_active_at": now}}
    )
    logger.info(f"[MEDIA] Saved full session video ({len(video_bytes)} bytes) to: {video_path}")
    return relative_url

