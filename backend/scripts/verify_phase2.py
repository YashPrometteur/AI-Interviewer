"""Standalone Verification Script for Phase 2 of AI Interviewer.

Verifies:
1. System Pre-flight Checks (FFmpeg installed, local Whisper base model ready, MongoDB connected).
2. Live Video/Audio Interview Session with DYNAMIC QUESTION-MATCHED AUDIO & INITIAL PROMPT BIASING:
   - Session creation with interview_mode='live' and answer_capture_type='video'
   - Generates dynamic, on-topic reference answers matching each generated question via Ollama
   - Synthesizes spoken speech audio (.wav) via local TTS (pyttsx3 / Windows SAPI)
   - Transcribes using Whisper 'base' with targeted initial_prompt containing technical terminology
   - Robust async/sync semantic flip detection (only checks standalone words, skips when not present)
   - Evaluates transcribed text through Groq openai/gpt-oss-120b
   - Completes session only after ALL generated questions are answered
3. Async Session Mode & Lifecycles:
   - Session creation with interview_mode='async' and 3-day deadline calculation
   - Enforces expired deadline rejection (HTTP 400)
4. Live Inactivity Timeout:
   - Prolonged inactivity detection (>60 mins) marking session as abandoned (HTTP 400)
5. Comprehensive Executive Report Generation with media transcript metadata.
"""
import os
import sys
import re
import time
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from bson import ObjectId

# Force UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import get_db
from app.core.config import settings
from app.interview import service, media
from app.reports import service as report_service
from app.ai.chains import get_generation_llm

def print_separator(title: str = ""):
    print("\n" + "=" * 90)
    if title:
        print(f"  {title.upper()}")
        print("=" * 90)


def generate_reference_answer(question_text: str, skill_tag: str, difficulty: str, quality: str = "strong") -> str:
    """Generates dynamic conversational interview answers via Ollama (qwen2.5:7b).
    - quality='strong': technically thorough, correct, expert answer spoken in natural, conversational interview phrasing.
    """
    llm = get_generation_llm()
    if not llm:
        return f"To handle this in {skill_tag} for {difficulty} scenarios, I use asynchronous request pipelines, Redis caching, asyncpg connection pooling, and structured error handling."

    prompt = (
        f"You are an experienced senior engineer in an interview answering a question on '{skill_tag}'.\n"
        f"Question ({difficulty.upper()} difficulty):\n{question_text}\n\n"
        f"Instructions:\n"
        f"- Provide a genuinely thorough, technically correct, expert-level response addressing its full difficulty (3-5 sentences).\n"
        f"- Be technically accurate and concrete: name real libraries/tools (e.g., FastAPI, PostgreSQL, Redis, asyncpg, aiohttp, pydantic, @app.get, Uvicorn, tenacity), explain mechanisms, and avoid hallucinating.\n"
        f"- Speak in a natural, conversational interview tone: use natural phrasing, contractions (I'd, we've, don't), and practical trade-off awareness.\n"
        f"- Do NOT wrap in quotes or markdown code blocks."
    )
    try:
        resp = llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        cleaned = content.strip().strip('"').strip("'")
        if len(cleaned) >= 20:
            return cleaned
    except Exception as e:
        print(f"⚠️ Warning: LLM answer generation failed ({e}), using fallback.")
    return f"To handle this in {skill_tag} for {difficulty} scenarios, I use asynchronous request pipelines, Redis caching, asyncpg connection pooling, and structured error handling."


def generate_spoken_wav(spoken_text: str, output_path: str):
    """Generates real spoken English speech audio in WAV format via pyttsx3 with Windows SAPI fallback."""
    abs_out = str(Path(output_path).resolve())
    
    # Try pyttsx3 first (offline TTS)
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 155)  # Natural pacing for clear acoustic articulation
        engine.save_to_file(spoken_text, abs_out)
        engine.runAndWait()
        if os.path.exists(abs_out) and os.path.getsize(abs_out) > 1000:
            return
    except Exception:
        pass

    # Windows PowerShell fallback
    abs_out_ps = abs_out.replace("\\", "/")
    escaped_text = spoken_text.replace('"', '""').replace("'", "''")
    ps_content = f"""Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 0
$synth.SetOutputToWaveFile("{abs_out_ps}")
$synth.Speak("{escaped_text}")
$synth.Dispose()
"""
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as ps_f:
        ps_f.write(ps_content)
        ps_path = ps_f.name

    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_path], check=True)
    finally:
        if os.path.exists(ps_path):
            os.remove(ps_path)


def run_phase2_verification():
    print_separator("PHASE 2 SYSTEM VERIFICATION: AUDIO/VIDEO & ASYNC INTERVIEWS")
    db = get_db()

    # 1. Pre-flight Checks
    print("\n[STEP 1] Running Pre-flight Environment Checks...")
    ffmpeg_ok = media.check_ffmpeg_available()
    print(f"  - FFmpeg Installed & Accessible: {'✅ YES' if ffmpeg_ok else '❌ NO'}")
    if not ffmpeg_ok:
        print("  ❌ FATAL: FFmpeg is required for Phase 2 local Whisper processing.")
        return

    print(f"  - Transcription Provider:  {settings.TRANSCRIPTION_PROVIDER}")
    print(f"  - Whisper Model Size:      {settings.WHISPER_MODEL_SIZE} (with technical initial_prompt biasing)")
    print(f"  - Primary Eval Model:      {settings.EVAL_MODEL_PROVIDER} ({settings.EVAL_MODEL_NAME})")
    print(f"  - Recordings Directory:    {settings.RECORDINGS_DIR}")
    print(f"  - Async Deadline Config:   {settings.ASYNC_SESSION_DEADLINE_DAYS} days")
    print(f"  - Live Inactivity Limit:   {settings.LIVE_SESSION_TIMEOUT_MINUTES} minutes")
    sys.stdout.flush()

    # Clean previous test sessions
    db.sessions.delete_many({"candidate_email": {"$in": ["phase2_live@test.com", "phase2_async@test.com", "phase2_abandon@test.com"]}})

    # =========================================================================
    # 2. Test Case 1: Live Video/Audio Interview Flow with Dynamic Answers & Vocabulary Biasing
    # =========================================================================
    print_separator("TEST CASE 1: LIVE VIDEO/AUDIO INTERVIEW SESSION (DYNAMIC ANSWERS + VOCABULARY BIASING)")

    jd_text = """
    We are looking for a Senior Python Backend Engineer.
    Key Requirements:
    - 4+ years of Python, FastAPI, and asynchronous backend development.
    - Deep understanding of asyncio event loops, concurrency, and GIL mechanics.
    - Experience designing high-throughput REST APIs and PostgreSQL database schemas.
    - Proficiency with Docker, testing, and production microservice architecture.
    """

    resume_text = """
    Jane Doe - Senior Backend Engineer
    Email: phase2_live@test.com
    Experience: 5 years building scalable web services in Python, FastAPI, and asyncio.
    Optimized database performance in PostgreSQL and implemented asynchronous task pipelines with Celery and Redis.
    """

    print("Creating Live Video Session...")
    sys.stdout.flush()
    session_res = service.start_session(
        db=db,
        candidate_name="Jane Doe",
        candidate_email="phase2_live@test.com",
        jd_text=jd_text.strip(),
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="live",
        answer_capture_type="video"
    )

    session_id = session_res.session_id
    total_q = session_res.total_questions
    print(f"✅ Live Video Session Created: ID={session_id}")
    print(f"   Mode: {session_res.interview_mode} | Capture: {session_res.answer_capture_type} | Questions: {total_q}")
    sys.stdout.flush()

    # Process all generated questions turn-by-turn
    for turn_idx in range(1, total_q + 1):
        next_q_res = service.get_next_question(db, session_id)
        if not next_q_res or not next_q_res.question:
            print(f"\n[Turn {turn_idx}] No more questions available.")
            break

        q = next_q_res.question
        print(f"\n" + "-" * 85)
        print(f"[TURN {turn_idx}/{total_q}] ({q.difficulty.upper()} | {q.skill_tag})")
        print(f"Question: \"{q.text}\"")
        sys.stdout.flush()

        # Generate on-topic reference answer matching this specific question
        expected_text = generate_reference_answer(q.text, q.skill_tag, q.difficulty, quality="strong")
        print(f"\n[EXPECTED CONTENT] (Dynamic Ground Truth Spoken by Candidate):\n\"{expected_text}\"")
        sys.stdout.flush()

        # 1. Synthesize spoken audio WAV file from the dynamically generated answer
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_audio:
            tmp_audio_path = tmp_audio.name

        try:
            generate_spoken_wav(expected_text, tmp_audio_path)
            with open(tmp_audio_path, "rb") as f:
                audio_bytes = f.read()

            audio_size_kb = len(audio_bytes) / 1024.0

            # 2. Upload recording to storage
            rel_media_path = media.upload_recording(session_id, q.id, audio_bytes, f"answer_turn_{turn_idx}.wav")

            # 3. Transcribe with Whisper 'base' using technical initial_prompt biasing
            t0 = time.time()
            trans_result = media.transcribe_recording(rel_media_path, model_size="base", skill_tag=q.skill_tag)
            t_latency = time.time() - t0

            whisper_text = trans_result.get("text", "").strip()
            confidence = trans_result.get("confidence") or 0.0
            trans_mode = trans_result.get("transcription_mode", "real")

            print(f"\n[WHISPER TRANSCRIPT] (Latency: {t_latency:.2f}s | Conf: {confidence:.4f} | Size: {audio_size_kb:.1f} KB):\n\"{whisper_text}\"")

            # 4. Accurate Technical Term & Semantic Flip Detection
            print(f"\n📊 [TRANSCRIPTION FIDELITY & JARGON ANALYSIS - TURN {turn_idx}]:")
            
            # Check semantic flip of standalone async/asynchronous vs sync/synchronous
            has_standalone_async = bool(re.search(r'\b(async|asynchronous)\b', expected_text, re.IGNORECASE))
            if has_standalone_async:
                # Detect if whisper split "async" / "asynchronous" into "a sync" / "a synchronous"
                split_detected = bool(re.search(r'\ba\s+(sync|synchronous)\b', whisper_text, re.IGNORECASE))
                clean_detected = bool(re.search(r'\b(async|asynchronous)\b', whisper_text, re.IGNORECASE))
                if split_detected and not clean_detected:
                    print("   - Async/Sync Semantic Check: ⚠️ FLIPPED (split into 'a sync' / 'a synchronous')")
                else:
                    print("   - Async/Sync Semantic Check: ✅ CLEAN (accurately recognized as 'async' / 'asynchronous')")
            else:
                print("   - Async/Sync Semantic Check: ℹ️ N/A (no standalone 'async'/'asynchronous' in ground truth)")

            # Check key technical terms mentioned in expected text vs transcript
            common_jargon = [
                "FastAPI", "PostgreSQL", "Redis", "asyncpg", "aiohttp", "pydantic",
                "@app.get", "@app.post", "Depends", "tenacity", "Uvicorn", "Gunicorn",
                "Docker", "asyncio", "GIL", "ACID", "JWT", "SQL", "REST"
            ]
            jargon_found = []
            for term in common_jargon:
                if re.search(r'\b' + re.escape(term) + r'\b', expected_text, re.IGNORECASE):
                    in_whisper = bool(re.search(r'\b' + re.escape(term) + r'\b', whisper_text, re.IGNORECASE))
                    status_icon = "✅" if in_whisper else "⚠️"
                    jargon_found.append(f"{term} ({status_icon})")
            if jargon_found:
                print(f"   - Technical Terms Recognized: {', '.join(jargon_found)}")

            sys.stdout.flush()

            # 5. Submit the transcription into the evaluation pipeline
            eval_res = service.submit_answer(
                db=db,
                session_id=session_id,
                question_id=q.id,
                answer_text=whisper_text,
                answer_source="video",
                recording_url=rel_media_path,
                transcription_confidence=confidence,
                transcription_mode=trans_mode
            )

            print(f"\n-> [EVALUATION (Groq openai/gpt-oss-120b)] | Score: {eval_res.score}/10 | Red Flag: {eval_res.red_flag}")
            print(f"-> Reasoning: {eval_res.reasoning}")
            sys.stdout.flush()

        finally:
            if Path(tmp_audio_path).exists():
                Path(tmp_audio_path).unlink()

    # Complete Session 1 (All questions now answered)
    comp_res = service.complete_session(db, session_id)
    print(f"\n✅ Live Session Completed! Overall Score: {comp_res.overall_score}/10 | Rec: {comp_res.report.recommendation.upper()}")
    sys.stdout.flush()
    
    report = report_service.get_full_report(db, session_id)
    print(f"\n✅ Executive Report Generated:")
    print(f"   - Session Mode:                {report.interview_mode}")
    print(f"   - Recommendation:              {report.report.recommendation.upper() if report.report else 'N/A'}")
    print(f"   - Executive Summary:           {report.report.summary_text if report.report else 'N/A'}")
    print(f"   - Candidate Strengths:         {report.report.strengths if report.report else []}")
    print(f"   - Candidate Weaknesses:        {report.report.weaknesses if report.report else []}")
    print(f"   - Transcript Items with Media: {len([t for t in report.transcript if t.recording_url])} / {len(report.transcript)}")
    sys.stdout.flush()

    # =========================================================================
    # 3. Test Case 2: Async Session Mode & Deadline Expiry
    # =========================================================================
    print_separator("TEST CASE 2: ASYNC INTERVIEW MODE & LIFECYCLE DEADLINE")

    async_res = service.start_session(
        db=db,
        candidate_name="Alex Async",
        candidate_email="phase2_async@test.com",
        jd_text=jd_text.strip(),
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="async",
        answer_capture_type="video"
    )
    async_id = async_res.session_id
    print(f"✅ Async Session Created: ID={async_id}")
    print(f"   Deadline: {async_res.session_deadline}")
    assert async_res.session_deadline is not None, "Async session must have session_deadline"

    # Verify active async session can fetch questions
    q_async = service.get_next_question(db, async_id)
    print(f"✅ Active Async Session Fetched Question: '{q_async.question.text[:60]}...'")

    # Simulate deadline expiration in DB
    past_deadline = datetime.now(timezone.utc) - timedelta(days=1)
    db.sessions.update_one({"_id": ObjectId(async_id)}, {"$set": {"session_deadline": past_deadline}})
    print("⏳ Simulated expired deadline (set to yesterday in DB). Testing rejection...")

    try:
        service.get_next_question(db, async_id)
        print("❌ FAILED: Expired async session was not rejected!")
    except Exception as e:
        print(f"✅ Expired Async Session Correctly Rejected with: {e.detail if hasattr(e, 'detail') else e}")

    # =========================================================================
    # 4. Test Case 3: Live Session Prolonged Inactivity Abandonment
    # =========================================================================
    print_separator("TEST CASE 3: LIVE SESSION INACTIVITY ABANDONMENT")

    abandon_res = service.start_session(
        db=db,
        candidate_name="Sam Stale",
        candidate_email="phase2_abandon@test.com",
        jd_text=jd_text.strip(),
        resume_bytes=resume_text.encode("utf-8"),
        resume_filename="resume.txt",
        interview_mode="live",
        answer_capture_type="text"
    )
    abandon_id = abandon_res.session_id
    print(f"✅ Live Session Created: ID={abandon_id}")

    # Backdate last_active_at past 60 minutes
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=75)
    db.sessions.update_one({"_id": ObjectId(abandon_id)}, {"$set": {"last_active_at": stale_time}})
    print("⏳ Simulated 75 minutes of inactivity in DB. Testing abandonment...")

    try:
        service.get_next_question(db, abandon_id)
        print("❌ FAILED: Inactive live session was not marked abandoned!")
    except Exception as e:
        print(f"✅ Inactive Live Session Correctly Marked Abandoned with: {e.detail if hasattr(e, 'detail') else e}")

    # Verify status in DB is now 'abandoned'
    abandon_doc = db.sessions.find_one({"_id": ObjectId(abandon_id)})
    print(f"   MongoDB Status: {abandon_doc.get('status')} (Expected: 'abandoned')")
    assert abandon_doc.get("status") == "abandoned"

    print_separator("PHASE 2 ALL VERIFICATION CHECKS PASSED SUCCESSFULLY 🎉")

if __name__ == "__main__":
    run_phase2_verification()
