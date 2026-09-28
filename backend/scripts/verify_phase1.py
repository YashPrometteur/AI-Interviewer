"""Standalone Verification Script for Phase 1 of AI Interviewer.

Runs 2 complete interview sessions end-to-end:
Session 1: Strong-Fit Senior Python/FastAPI Candidate
Session 2: Weak-Fit / Mismatched Candidate (Sales resume for Backend role)

Submits strong technical answers vs deliberately weak/gibberish answers to print the generated
questions, scores, reasoning, red flags, evaluation provider tiers, and executive summary.
"""
import os
import sys
import json
import random
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import get_db, database
from app.interview import service
from app.reports import service as report_service
from app.ai.chains import get_generation_llm, evaluate_answer
from app.core.config import settings

def print_separator(title: str = ""):
    print("\n" + "=" * 90)
    if title:
        print(f"  {title.upper()}")
        print("=" * 90)

def print_session_created_status(session_num: int, res):
    """Prints session creation status with a prominent visual warning banner if in Mock Mode."""
    print(f"Session Created! ID: {res.session_id} | Total Generated Questions: {res.total_questions}")
    if res.mock:
        print("\n" + "!" * 90)
        print(f"  ⚠️  WARNING: TEST CASE {session_num} IS RUNNING IN MOCK MODE (MOCK: TRUE)!")
        print("  AI generation failed or fell back to hardcoded mock templates.")
        print("!" * 90 + "\n")
    else:
        print(f"Mock Mode: False (Live Ollama Question Generation Active)")
    sys.stdout.flush()

def generate_reference_answer(question_text: str, skill_tag: str, difficulty: str, quality: str = "strong") -> str:
    """Generates dynamic human-sounding conversational interview answers via Ollama (qwen2.5:7b).
    - quality='strong': technically thorough, correct, expert answer spoken in natural, conversational interview phrasing.
    - quality='weak': vague/incomplete answer verified via evaluate_answer() self-check loop (score < 6.0).
    - quality='alternate': technically correct answer using an alternative, less conventional but valid approach.
    """
    llm = get_generation_llm()
    if not llm:
        if quality == "strong":
            return f"Yeah, so in {skill_tag} when handling this for {difficulty} scenarios, I'd usually set up structured pattern handling, make sure we optimize connection latency, and keep error recovery clean."
        elif quality == "alternate":
            return f"Honestly, an alternate way to tackle this in {skill_tag} instead of the standard pattern is using lightweight in-process caching or direct event dispatching, which cuts down overhead."
        else:
            return f"Uh, so basically I think {skill_tag} is just about running queries or loops, but I always mix up the mutability and internal methods, so I usually just guess or let the framework handle it."

    if quality == "strong":
        prompt = (
            f"You are an experienced senior engineer in an interview answering a question on '{skill_tag}'.\n"
            f"Question ({difficulty.upper()} difficulty):\n{question_text}\n\n"
            f"Instructions:\n"
            f"- Provide a genuinely thorough, technically correct, expert-level response addressing its full difficulty (3-5 sentences).\n"
            f"- Be technically accurate and concrete: name real libraries/tools, explain specific mechanisms (e.g. Redis sliding window / token bucket, async middleware, indexes), and avoid hallucinating non-existent library modules.\n"
            f"- Speak in a natural, conversational interview tone: use natural phrasing, contractions (I'd, we've, don't), "
            f"occasional thinking phrases ('so basically', 'honestly depends on scale, but...'), and practical trade-off awareness.\n"
            f"- Do NOT wrap in quotes or markdown code blocks."
        )
        try:
            resp = llm.invoke(prompt)
            content = resp.content if hasattr(resp, "content") else str(resp)
            cleaned = content.strip().strip('"').strip("'")
            if len(cleaned) >= 20:
                return cleaned
        except Exception:
            pass
        return f"Yeah, so in {skill_tag} when handling this for {difficulty} scenarios, I'd usually set up structured pattern handling, make sure we optimize connection latency, and keep error recovery clean."

    elif quality == "alternate":
        prompt = (
            f"You are an experienced engineer in an interview answering a question on '{skill_tag}'.\n"
            f"Question ({difficulty.upper()} difficulty):\n{question_text}\n\n"
            f"Instructions:\n"
            f"- Provide a genuinely correct, technically sound answer (3-5 sentences), but intentionally solve or address this question "
            f"using an ALTERNATIVE, valid approach, library, or architectural pattern than the most standard textbook one "
            f"(e.g., event-driven vs polling, in-memory sliding window vs Redis token bucket, custom middleware vs third-party dependency, CTEs vs window subqueries).\n"
            f"- Explain why this alternate approach is practical and valid for certain trade-offs.\n"
            f"- Speak in a natural, conversational interview tone.\n"
            f"- Do NOT wrap in quotes or markdown code blocks."
        )
        try:
            resp = llm.invoke(prompt)
            content = resp.content if hasattr(resp, "content") else str(resp)
            cleaned = content.strip().strip('"').strip("'")
            if len(cleaned) >= 20:
                return cleaned
        except Exception:
            pass
        return f"Honestly, an alternate way to tackle this in {skill_tag} instead of the standard pattern is using lightweight in-process caching or direct event dispatching, which cuts down overhead."

    else:
        # quality == "weak": Self-check verification loop (target score < 6.0)
        weak_flaws = [
            "Confuse the core concepts (e.g. claim LEFT JOIN only returns non-matching rows, or claim lists are immutable while tuples are mutable, or confuse HTTP status codes). State this wrong fact confidently with casual phrasing.",
            "Give a technically incorrect definition and provide a broken or nonsensical code/logic example.",
            "Answer a completely different topic (e.g. talk about installing packages or restarting servers instead of answering what was asked).",
            "Give a completely superficial non-answer saying you usually just google it, don't remember the details, or let an ORM/library figure it out."
        ]

        last_weak_answer = ""
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            if attempt == 1:
                gap_instruction = (
                    "Even for simple questions, the answer must be substantively incomplete or flawed. "
                    "Do not provide a full, accurate explanation. Missing key syntax, confusing concepts, or omitting definitions is required (2-3 sentences)."
                )
            elif attempt == 2:
                chosen_flaw = random.choice(weak_flaws)
                gap_instruction = (
                    f"MANDATORY FLAW REQUIREMENT: You are roleplaying a candidate who lacks solid knowledge on this question.\n"
                    f"Flaw Strategy: {chosen_flaw}\n"
                    f"DO NOT give a correct or accurate explanation. The answer MUST contain an obvious mistake or omission so that it scores under 6.0/10."
                )
            else:
                # 3rd / final retry attempt: deterministic concrete factual error
                gap_instruction = (
                    "Include one clearly incorrect technical claim about this topic stated confidently, "
                    "as if the candidate misremembers a key detail, while keeping the rest of the answer's delivery natural and conversational (2-3 sentences)."
                )

            prompt = (
                f"You are a candidate taking a technical interview on '{skill_tag}'.\n"
                f"Question ({difficulty.upper()} difficulty):\n{question_text}\n\n"
                f"Instructions:\n"
                f"1. Style: Speak in a natural, casual, conversational interview tone with filler words and contractions ('uh so basically', 'I usually just...', 'I think', 'honestly').\n"
                f"2. Content: {gap_instruction}\n"
                f"- Do NOT wrap in quotes or markdown code blocks."
            )

            try:
                resp = llm.invoke(prompt)
                content = resp.content if hasattr(resp, "content") else str(resp)
                candidate_ans = content.strip().strip('"').strip("'")
                if len(candidate_ans) >= 15:
                    last_weak_answer = candidate_ans
                    # Immediate evaluation self-check
                    eval_check = evaluate_answer(question_text, skill_tag, candidate_ans)
                    score = float(eval_check.get("score", 10.0))
                    if score < 6.0:
                        return candidate_ans
                    else:
                        print(f"      [Weak-Answer Self-Check] Attempt {attempt}/{max_attempts} scored {score}/10 (>= 6.0). Retrying with specific flaw constraint...")
                        sys.stdout.flush()
            except Exception:
                pass

        # 3 attempts exhausted
        print("      ⚠️ COULD NOT GENERATE SUFFICIENTLY WEAK ANSWER AFTER 3 ATTEMPTS")
        sys.stdout.flush()
        if last_weak_answer:
            return last_weak_answer
        return f"Uh, so basically I think {skill_tag} is just about running queries or loops, but I always mix up the mutability and internal methods, so I usually just guess or let the framework handle it."

def print_session_score_summary(session_scores: dict):
    """Prints score summary and flags an explicit warning if Weak score >= Strong score."""
    if "strong" in session_scores and "weak" in session_scores:
        delta = session_scores["strong"] - session_scores["weak"]
        alt_str = f" | Alternate: {session_scores['alternate']}/10" if "alternate" in session_scores else ""
        print(f"\n      -> [SCORE SUMMARY]: Strong: {session_scores['strong']}/10{alt_str} | Weak: {session_scores['weak']}/10 | Delta (Strong - Weak): {delta:+.1f} pts")
        if session_scores["weak"] >= session_scores["strong"]:
            print(f"      -> ⚠️ TEST DATA WARNING: Weak score ({session_scores['weak']}/10) >= Strong score ({session_scores['strong']}/10) — weak answer generation was not sufficiently flawed!")
        sys.stdout.flush()

def run_verification():
    # Connect to MongoDB
    db = get_db()

    print_separator("PHASE 1 AI INTERVIEWER VERIFICATION SCRIPT")
    print(f"Generation Model:       {settings.GENERATION_MODEL_PROVIDER} ({settings.GENERATION_MODEL_NAME})")
    print(f"Primary Eval Model:     {settings.EVAL_MODEL_PROVIDER} ({settings.EVAL_MODEL_NAME})")
    print(f"Fallback Eval Model:    {settings.EVAL_FALLBACK_MODEL_PROVIDER} ({settings.EVAL_FALLBACK_MODEL_NAME})")
    print(f"Groq API Key Set:       {'YES' if settings.GROQ_API_KEY else 'NO'}")
    print(f"Ollama Endpoint:        {settings.OLLAMA_BASE_URL}")
    sys.stdout.flush()

    # =========================================================================
    # TEST CASE 1: STRONG FIT CANDIDATE (Senior Python Backend Engineer)
    # =========================================================================
    print_separator("TEST CASE 1: Strong-Fit Senior Python Backend Candidate")

    jd_strong = """
    Senior Python Backend Engineer
    We are seeking a Senior Backend Engineer proficient in Python, FastAPI, PostgreSQL, and distributed system design.
    Responsibilities:
    - Architect and scale low-latency REST and async APIs using FastAPI and SQLAlchemy.
    - Design and optimize complex relational schemas in PostgreSQL with indexes and connection pooling.
    - Implement caching with Redis and maintain CI/CD automated test pipelines.
    - Mentor junior engineers and conduct technical code reviews.
    """

    resume_strong = """
    Alex Rivera - Senior Software Engineer (alex.rivera@example.com)
    Experience:
    - 6+ years designing high-throughput backend services in Python, FastAPI, and Django.
    - Led migration of monolithic database to PostgreSQL with read replicas, reducing query latency by 45%.
    - Built Redis caching layers and asynchronous task queues with Celery handling 10k req/sec.
    - Deep knowledge of ACID transactions, database indexing, and microservice architectures.
    """

    print("\n[1.1] Creating Session 1 (Parsing JD + Resume)...")
    sys.stdout.flush()
    res1 = service.start_session(
        db=db,
        candidate_name="Alex Rivera",
        candidate_email="alex.rivera@example.com",
        jd_text=jd_strong,
        resume_bytes=resume_strong.encode("utf-8"),
        resume_filename="alex_rivera_resume.txt"
    )
    print_session_created_status(1, res1)
    sys.stdout.flush()

    # Turn-by-turn question fetching & dynamic answer generation for Session 1
    session1_turns = [
        ("strong", "Human-Sounding Strong Technical Answer"),
        ("weak", "Human-Sounding Weak/Vague Answer"),
        ("alternate", "[ALTERNATE APPROACH ANSWER] (Valid Alternative Architecture)")
    ]

    session1_scores = {}
    for turn_num, (quality, quality_label) in enumerate(session1_turns, start=1):
        q_resp = service.get_next_question(db, res1.session_id)
        if not q_resp or not q_resp.question:
            print(f"\n[1.{turn_num * 2}] No more questions available for Turn {turn_num}.")
            sys.stdout.flush()
            break

        q = q_resp.question
        # 1. Print Turn Number and Question Details
        print(f"\n[1.{turn_num * 2}] Turn {turn_num} Question ({q.skill_tag} - {q.difficulty}):")
        print(f"      \"{q.text}\"")

        # 2. Generate and Print Dynamic Answer
        answer_text = generate_reference_answer(q.text, q.skill_tag, q.difficulty, quality=quality)
        print(f"\n[1.{turn_num * 2 + 1}] Submitting {quality_label} for Turn {turn_num}:")
        print(f"      \"{answer_text}\"")
        sys.stdout.flush()

        # 3. Submit Answer and Print Evaluation Tier, Score, Red Flag, and Reasoning
        eval_res = service.submit_answer(db, res1.session_id, q.id, answer_text)
        session1_scores[quality] = eval_res.score
        print(f"\n      -> [EVAL TIER: {eval_res.eval_provider}] | Score: {eval_res.score}/10 | Red Flag: {eval_res.red_flag}")
        print(f"      -> Reasoning: {eval_res.reasoning}")
        sys.stdout.flush()

    # Print Score Comparison & Delta for Session 1
    print_session_score_summary(session1_scores)

    # Finalize Session 1 and Print Report
    print("\n[1.6] Completing Session 1 & Generating Executive Report...")
    sys.stdout.flush()
    complete1 = service.complete_session(db, res1.session_id)
    print(f"Final Weighted Score: {complete1.overall_score}/10")
    print(f"Eval Tier:            {complete1.eval_provider}")
    print(f"Recommendation:       {complete1.report.recommendation.upper()}")
    print(f"Summary:              {complete1.report.summary_text}")
    print(f"Strengths:            {complete1.report.strengths}")
    print(f"Weaknesses:           {complete1.report.weaknesses}")
    sys.stdout.flush()


    # =========================================================================
    # TEST CASE 2: WEAK FIT / MISMATCHED CANDIDATE
    # =========================================================================
    print_separator("TEST CASE 2: Weak-Fit / Mismatched Candidate (Sales Resume for Senior Backend Role)")

    resume_weak = """
    Jordan Miller - Retail Sales Associate & Customer Success (jordan.m@example.com)
    Experience:
    - 4 years in retail sales, inventory counting, and POS checkout management.
    - Cold calling enterprise leads and organizing regional marketing events.
    - Proficient in Microsoft Excel and Salesforce CRM.
    """

    print("\n[2.1] Creating Session 2 (Parsing JD + Sales Resume)...")
    sys.stdout.flush()
    res2 = service.start_session(
        db=db,
        candidate_name="Jordan Miller",
        candidate_email="jordan.m@example.com",
        jd_text=jd_strong,
        resume_bytes=resume_weak.encode("utf-8"),
        resume_filename="jordan_miller_sales.txt"
    )
    print_session_created_status(2, res2)
    sys.stdout.flush()

    # Turn-by-turn question fetching & answer submission for Session 2
    session2_answers = [
        # Turn 1 Answer (Deliberately weak / gibberish answer)
        "idk honestly i do sales not python coding lol asdf",
        # Turn 2 Answer (Evasive non-technical answer)
        "I just click buttons on the screen and have never worked with databases or backend servers."
    ]

    for turn_num, answer_text in enumerate(session2_answers, start=1):
        q_resp = service.get_next_question(db, res2.session_id)
        if not q_resp or not q_resp.question:
            print(f"\n[2.{turn_num * 2}] No more questions available for Turn {turn_num}.")
            sys.stdout.flush()
            break

        qw = q_resp.question
        # 1. Print Turn Number and Question Details
        print(f"\n[2.{turn_num * 2}] Turn {turn_num} Question ({qw.skill_tag} - {qw.difficulty}):")
        print(f"      \"{qw.text}\"")

        # 2. Print Exact Submitted Answer
        print(f"\n[2.{turn_num * 2 + 1}] Submitting Answer for Turn {turn_num}:")
        print(f"      \"{answer_text}\"")
        sys.stdout.flush()

        # 3. Submit Answer and Print Evaluation Tier, Score, Red Flag, and Reasoning
        eval_w = service.submit_answer(db, res2.session_id, qw.id, answer_text)
        print(f"\n      -> [EVAL TIER: {eval_w.eval_provider}] | Score: {eval_w.score}/10 | Red Flag: {eval_w.red_flag}")
        print(f"      -> Reasoning: {eval_w.reasoning}")
        sys.stdout.flush()

    # Finalize Session 2 and Print Report
    print("\n[2.6] Completing Session 2 & Generating Executive Report...")
    sys.stdout.flush()
    complete2 = service.complete_session(db, res2.session_id)
    print(f"Final Weighted Score: {complete2.overall_score}/10")
    print(f"Eval Tier:            {complete2.eval_provider}")
    print(f"Recommendation:       {complete2.report.recommendation.upper()}")
    print(f"Summary:              {complete2.report.summary_text}")
    print(f"Strengths:            {complete2.report.strengths}")
    print(f"Weaknesses:           {complete2.report.weaknesses}")
    sys.stdout.flush()


    # =========================================================================
    # TEST CASE 3: DATA ANALYST ROLE (STRONG-FIT CANDIDATE)
    # =========================================================================
    print_separator("TEST CASE 3: Strong-Fit Data Analyst Candidate")

    jd_da = """
    We are hiring a Data Analyst to join our analytics team. Responsibilities include writing 
    complex SQL queries to extract and transform data from relational databases, building 
    dashboards and reports using tools like Tableau or Power BI, performing statistical analysis 
    to identify trends, and using Python (pandas, numpy) for data cleaning and exploratory 
    analysis. Strong communication skills to present findings to non-technical stakeholders are 
    required.
    """

    resume_da = """
    Taylor Morgan - Data Analyst (taylor.m@example.com)
    Experience:
    - 3 years of experience as a Data Analyst. Proficient in SQL (joins, window functions, CTEs), Python (pandas, numpy, matplotlib), and Tableau dashboard creation.
    - Built automated reporting pipelines reducing manual reporting time by 40%.
    - Regularly presented quarterly business insights to leadership.
    """

    print("\n[3.1] Creating Session 3 (Parsing JD + Data Analyst Resume)...")
    sys.stdout.flush()
    res3 = service.start_session(
        db=db,
        candidate_name="Taylor Morgan",
        candidate_email="taylor.m@example.com",
        jd_text=jd_da,
        resume_bytes=resume_da.encode("utf-8"),
        resume_filename="taylor_morgan_data_analyst.txt"
    )
    print_session_created_status(3, res3)
    sys.stdout.flush()
    sys.stdout.flush()

    # Turn-by-turn question fetching & dynamic answer generation for Session 3
    session3_turns = [
        ("strong", "Human-Sounding Strong Technical Answer"),
        ("weak", "Human-Sounding Weak/Vague Answer"),
        ("alternate", "[ALTERNATE APPROACH ANSWER] (Valid Alternative Analytics Method)")
    ]

    session3_scores = {}
    for turn_num, (quality, quality_label) in enumerate(session3_turns, start=1):
        q_resp = service.get_next_question(db, res3.session_id)
        if not q_resp or not q_resp.question:
            print(f"\n[3.{turn_num * 2}] No more questions available for Turn {turn_num}.")
            sys.stdout.flush()
            break

        q = q_resp.question
        # 1. Print Turn Number and Question Details
        print(f"\n[3.{turn_num * 2}] Turn {turn_num} Question ({q.skill_tag} - {q.difficulty}):")
        print(f"      \"{q.text}\"")

        # 2. Generate and Print Dynamic Answer
        answer_text = generate_reference_answer(q.text, q.skill_tag, q.difficulty, quality=quality)
        print(f"\n[3.{turn_num * 2 + 1}] Submitting {quality_label} for Turn {turn_num}:")
        print(f"      \"{answer_text}\"")
        sys.stdout.flush()

        # 3. Submit Answer and Print Evaluation Tier, Score, Red Flag, and Reasoning
        eval_res = service.submit_answer(db, res3.session_id, q.id, answer_text)
        session3_scores[quality] = eval_res.score
        print(f"\n      -> [EVAL TIER: {eval_res.eval_provider}] | Score: {eval_res.score}/10 | Red Flag: {eval_res.red_flag}")
        print(f"      -> Reasoning: {eval_res.reasoning}")
        sys.stdout.flush()

    # Print Score Comparison & Delta for Session 3
    print_session_score_summary(session3_scores)

    # Finalize Session 3 and Print Report
    print("\n[3.6] Completing Session 3 & Generating Executive Report...")
    sys.stdout.flush()
    complete3 = service.complete_session(db, res3.session_id)
    print(f"Final Weighted Score: {complete3.overall_score}/10")
    print(f"Eval Tier:            {complete3.eval_provider}")
    print(f"Recommendation:       {complete3.report.recommendation.upper()}")
    print(f"Summary:              {complete3.report.summary_text}")
    print(f"Strengths:            {complete3.report.strengths}")
    print(f"Weaknesses:           {complete3.report.weaknesses}")
    sys.stdout.flush()

    print_separator("VERIFICATION COMPLETED SUCCESSFULLY")

if __name__ == "__main__":
    run_verification()
