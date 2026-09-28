"""Phase 1: LangChain AI prompt chains and multi-tier model routing.
Generation routes through Ollama (qwen2.5:7b).
Evaluation follows a multi-tier fallback chain: Groq (llama-3.3-70b-versatile) -> Ollama (qwen2.5:7b) -> Heuristic Mock.
Every evaluation and summary is tagged with its active provider tier: 'groq' | 'ollama_fallback' | 'mock'.
"""
import json
import logging
import re
import socket
import urllib.parse
from typing import List, Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger("ai_interviewer")

def is_ollama_reachable(base_url: str) -> bool:
    """Fast non-blocking socket check to verify if Ollama daemon is currently running."""
    try:
        parsed = urllib.parse.urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 11434
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        res = sock.connect_ex((host, port))
        sock.close()
        return res == 0
    except Exception:
        return False

# --- Provider LLM Factory ---
def create_llm_client(provider: str, model_name: str, temperature: float = 0.2):
    """Creates a LangChain chat model for Ollama, Groq, or OpenAI."""
    provider_lower = (provider or "").lower().strip()

    if provider_lower == "ollama":
        if not is_ollama_reachable(settings.OLLAMA_BASE_URL):
            return None
        try:
            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                from langchain_community.chat_models import ChatOllama

            return ChatOllama(
                base_url=settings.OLLAMA_BASE_URL,
                model=model_name or settings.GENERATION_MODEL_NAME,
                temperature=temperature,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize ChatOllama ({e}).")
            return None

    elif provider_lower == "groq":
        if not settings.GROQ_API_KEY:
            return None
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                api_key=settings.GROQ_API_KEY,
                model_name=model_name or settings.EVAL_MODEL_NAME,
                temperature=temperature,
                max_retries=1,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize ChatGroq ({e}).")
            return None

    elif provider_lower == "openai":
        if not settings.OPENAI_API_KEY:
            return None
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                api_key=settings.OPENAI_API_KEY,
                model=model_name or settings.OPENAI_MODEL,
                temperature=temperature,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize ChatOpenAI ({e}).")
            return None

    return None

def get_generation_llm():
    """Returns the ultra-fast generation LLM (Groq with automatic Ollama fallback)."""
    llm = create_llm_client(
        provider=settings.GENERATION_MODEL_PROVIDER,
        model_name=settings.GENERATION_MODEL_NAME,
        temperature=0.7
    )
    if not llm:
        if settings.GENERATION_MODEL_PROVIDER != "ollama" and is_ollama_reachable(settings.OLLAMA_BASE_URL):
            llm = create_llm_client(
                provider="ollama",
                model_name=settings.OLLAMA_MODEL,
                temperature=0.7
            )
        elif settings.GROQ_API_KEY:
            llm = create_llm_client(
                provider="groq",
                model_name="qwen/qwen3.8-27b",
                temperature=0.7
            )
    return llm

def clean_and_parse_json(text: str) -> Any:
    """Extracts and parses JSON object/array from LLM response text, ignoring markdown backticks and surrounding text."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try raw_decode starting from first '{' or '[' to cleanly ignore trailing commentary
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(text[i:])
                return obj
            except json.JSONDecodeError:
                continue

    obj_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if obj_match:
        return json.loads(obj_match.group(1).strip())
    raise json.JSONDecodeError("Could not extract valid JSON object or array", text, 0)


# --- 1. Extract Skills Chain (Ollama) ---
def extract_skills_chain(jd_text: str) -> Dict[str, Any]:
    """Extracts key required technical/domain skills from JD using Ollama (qwen2.5:7b)."""
    llm = get_generation_llm()
    if not llm:
        logger.info("[GENERATION] Ollama unavailable, extract_skills_chain falling back to mock.")
        return extract_skills_mock(jd_text)

    prompt = (
        "You are an expert technical recruiter and hiring architect.\n"
        "Analyze the following Job Description (JD) and extract the top 3-5 distinct required skills or technical competencies.\n"
        "Assign an importance weight to each skill such that the sum of all weights strictly equals 1.0.\n\n"
        f"Job Description:\n{jd_text}\n\n"
        "CRITICAL INSTRUCTION: Return ONLY the JSON array. Do not include any explanation, commentary, or text before or after the JSON. Do not wrap it in markdown code blocks.\n\n"
        "JSON schema:\n"
        "[\n"
        "  {\"skill\": \"Skill Name\", \"weight\": 0.35},\n"
        "  {\"skill\": \"Skill Name\", \"weight\": 0.35},\n"
        "  {\"skill\": \"Skill Name\", \"weight\": 0.30}\n"
        "]"
    )

    try:
        response = llm.invoke(prompt)
        parsed = clean_and_parse_json(response.content if hasattr(response, 'content') else str(response))
        total_w = sum(float(item.get("weight", 0)) for item in parsed)
        if total_w > 0:
            for item in parsed:
                item["weight"] = round(float(item["weight"]) / total_w, 2)
        return {"skills": parsed, "mock": False}
    except Exception as e:
        logger.warning(f"[GENERATION] Ollama extract_skills failed ({e}). Falling back to mock.")
        return extract_skills_mock(jd_text)


def extract_skills_mock(jd_text: str) -> Dict[str, Any]:
    detected = []
    lower = jd_text.lower()
    if "python" in lower or "fastapi" in lower or "django" in lower:
        detected.append("Python Backend")
    if "react" in lower or "next" in lower or "typescript" in lower or "javascript" in lower:
        detected.append("Frontend / TypeScript")
    if "sql" in lower or "database" in lower or "postgres" in lower:
        detected.append("Database & SQL")
    if "docker" in lower or "aws" in lower or "cloud" in lower or "system" in lower:
        detected.append("System Architecture")
    
    if not detected:
        detected = ["Core Backend Architecture", "API Design & Data Modeling", "Problem Solving & Testing"]
    
    weight = round(1.0 / len(detected), 2)
    skills = [{"skill": s, "weight": weight} for s in detected]
    total = sum(s["weight"] for s in skills)
    if skills and total > 0:
        skills[0]["weight"] = round(skills[0]["weight"] + (1.0 - total), 2)

    return {"skills": skills, "mock": True}


# --- 2. Extract Candidate Background Chain (Ollama) ---
def extract_background_chain(resume_text: str, skills: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarizes candidate's relevant experience per skill found in the JD using Ollama."""
    llm = get_generation_llm()
    skill_names = [s.get("skill", "") for s in skills]

    if not llm:
        logger.info("[GENERATION] Ollama unavailable, extract_background_chain falling back to mock.")
        summary = {s: f"Demonstrated background matching {s} based on resume analysis." for s in skill_names}
        return {"background": summary, "mock": True}

    prompt = (
        "You are an expert technical interviewer.\n"
        f"Review the candidate's resume and summarize their demonstrated experience specifically for each of these target skills: {skill_names}.\n"
        "If the candidate has little or no relevant experience for a skill, clearly state 'Little to no demonstrated experience'.\n\n"
        f"Resume Text:\n{resume_text}\n\n"
        "CRITICAL INSTRUCTION: Return ONLY a valid JSON object with no commentary or markdown code blocks.\n"
        "Example:\n"
        "{\n"
        "  \"Skill A\": \"3 years building APIs using FastAPI and PostgreSQL.\",\n"
        "  \"Skill B\": \"Limited exposure noted on resume.\"\n"
        "}"
    )

    try:
        response = llm.invoke(prompt)
        parsed = clean_and_parse_json(response.content if hasattr(response, 'content') else str(response))
        return {"background": parsed, "mock": False}
    except Exception as e:
        logger.warning(f"[GENERATION] Ollama extract_background failed ({e}). Falling back to mock.")
        summary = {s: f"Candidate background evaluated for {s}." for s in skill_names}
        return {"background": summary, "mock": True}


# --- 3. Generate Questions Chain (Groq / Ollama) ---
def generate_questions(jd_skills: List[Dict[str, Any]], resume_summary: Dict[str, Any]) -> Dict[str, Any]:
    """Generates EXACTLY 3 tailored progressive questions for the entire interview (1 easy, 1 medium, 1 hard)."""
    llm = get_generation_llm()

    if not llm:
        logger.info("[GENERATION] LLM unavailable, generate_questions falling back to mock.")
        return generate_questions_mock(jd_skills)

    prompt = (
        "You are an expert technical interviewer conducting a strictly CONVERSATIONAL, SPOKEN technical interview.\n"
        "Generate EXACTLY 3 progressive, purely conceptual and theoretical questions for the ENTIRE interview covering the candidate's top required skills and demonstrated background:\n"
        "- Question 1: 'easy' (Core fundamentals, data structures, mutability, language mechanics, or basic OOP tailored to the primary skill)\n"
        "- Question 2: 'medium' (Applied theory, trade-offs, concurrency/caching mechanics, query optimization concepts, or debugging approach on secondary skill)\n"
        "- Question 3: 'hard' (High-level architecture, scalability trade-offs, distributed design, or failure recovery on system skills)\n\n"
        "STRICT SPOKEN INTERVIEW RULES:\n"
        "1. NO CODING QUESTIONS: DO NOT ask the candidate to write code, write syntax, recite regex, or write SQL queries. Every question must be fully answerable in spoken words.\n"
        "2. CONVERSATIONAL & REASONING FOCUS: Ask questions that require verbal explanation of concepts, trade-offs, internal mechanics, or architectural choices (e.g. 'Can you explain the conceptual difference between...', 'What are the trade-offs of...', 'How does the event loop/engine handle...').\n"
        "3. DIVERSE FUNDAMENTALS: For the easy question, freely test core foundational concepts (such as data structure choices, mutability, memory trade-offs, variable scope, OOP principles, or HTTP semantics), rotating topics dynamically based on the candidate's resume and job requirements.\n\n"
        "DIFFICULTY TIERS:\n"
        "- 'easy': Core conceptual fundamentals (e.g. mutability and hashing, lists vs sets vs tuples memory/lookup characteristics, shallow vs deep copying, synchronous vs asynchronous execution basics, HTTP status codes and REST principles, basic database key constraints).\n"
        "- 'medium': Applied theory and trade-offs (e.g. async event loop mechanics vs multithreading, database indexing mechanisms like B-Tree vs sequential scans and write penalties, connection pooling, caching invalidation strategies, rate limiting algorithms like token bucket, API middleware lifecycle).\n"
        "- 'hard': System design and architecture (e.g. high-throughput scaling trade-offs, message queues vs log streams like RabbitMQ vs Kafka, database sharding and replication consistency models, circuit breaker patterns, real-time WebSockets vs polling trade-offs, microservice failure resilience).\n\n"
        f"Target Skills & Weights: {json.dumps(jd_skills)}\n"
        f"Candidate Background Summary: {json.dumps(resume_summary)}\n\n"
        "CRITICAL INSTRUCTION: Return ONLY a valid JSON array of EXACTLY 3 questions. Do not include any commentary, explanation, markdown formatting, or preamble.\n\n"
        "JSON array format:\n"
        "[\n"
        "  {\"text\": \"Clear, spoken theoretical easy question text...\", \"skill_tag\": \"Skill Name\", \"difficulty\": \"easy\"},\n"
        "  {\"text\": \"Clear, spoken trade-off medium question text...\", \"skill_tag\": \"Skill Name\", \"difficulty\": \"medium\"},\n"
        "  {\"text\": \"Clear, spoken architecture hard question text...\", \"skill_tag\": \"Skill Name\", \"difficulty\": \"hard\"}\n"
        "]"
    )

    last_err = None
    for attempt in range(2):
        response = llm.invoke(prompt)
        raw_text = response.content if hasattr(response, 'content') else str(response)
        try:
            parsed = clean_and_parse_json(raw_text)
            q_list = []
            if isinstance(parsed, list) and len(parsed) > 0:
                q_list = parsed
            elif isinstance(parsed, dict) and "questions" in parsed:
                q_list = parsed["questions"]

            if q_list:
                # Ensure exactly 3 questions (1 easy, 1 medium, 1 hard if available)
                if len(q_list) > 3:
                    easy_q = [q for q in q_list if (q.get("difficulty") or "").lower() == "easy"]
                    med_q = [q for q in q_list if (q.get("difficulty") or "").lower() == "medium"]
                    hard_q = [q for q in q_list if (q.get("difficulty") or "").lower() == "hard"]
                    selected = []
                    if easy_q: selected.append(easy_q[0])
                    if med_q: selected.append(med_q[0])
                    if hard_q: selected.append(hard_q[0])
                    # Fill any remaining slots if tier filter didn't catch 3
                    for q in q_list:
                        if q not in selected and len(selected) < 3:
                            selected.append(q)
                    q_list = selected[:3]
                return {"questions": q_list[:3], "mock": False}
            else:
                raise ValueError(f"Expected non-empty list of questions, got: {type(parsed)}")
        except Exception as e:
            last_err = e
            logger.warning(
                f"[GENERATION] Question generation JSON parse error on attempt {attempt + 1}/2. Error: {e}"
            )
            if attempt == 0:
                logger.info("[GENERATION] Retrying question generation with same prompt...")

    logger.warning(f"[GENERATION] LLM generate_questions falling back to mock after retries failed. ({last_err})")
    return generate_questions_mock(jd_skills)


def generate_questions_mock(jd_skills: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates exactly 3 progressive spoken theoretical questions total across the candidate's top skills."""
    skills = [s.get("skill", "Core") for s in jd_skills]
    s1 = skills[0] if len(skills) > 0 else "Python Backend"
    s2 = skills[1] if len(skills) > 1 else s1
    s3 = skills[2] if len(skills) > 2 else (skills[1] if len(skills) > 1 else s1)

    questions = [
        {"text": f"Can you explain the core concepts, memory characteristics, and mutability principles in {s1}?", "skill_tag": s1, "difficulty": "easy"},
        {"text": f"What are the major performance trade-offs, concurrency handling, or indexing strategies when optimizing {s2} in production?", "skill_tag": s2, "difficulty": "medium"},
        {"text": f"How would you architect a high-throughput, fault-tolerant distributed system utilizing {s3}, and what failure modes would you design against?", "skill_tag": s3, "difficulty": "hard"}
    ]
    return {"questions": questions, "mock": True}


# --- 4. Evaluate Answer Chain with Combined Dynamic Follow-Up (Groq -> Ollama -> Mock) ---
def evaluate_answer_mock_heuristic(question: str, skill_tag: str, answer_text: str) -> Dict[str, Any]:
    """Keyword-aware heuristic fallback for Mock Mode (used only when both Groq and Ollama fail)."""
    cleaned = (answer_text or "").strip().lower()
    
    negative_triggers = ["idk", "dont know", "no idea", "asdf", "test", "not coding", "sales", "retail", "lol", "i do sales", "not a developer"]
    if any(trigger in cleaned for trigger in negative_triggers) or len(cleaned.split()) < 5:
        return {
            "score": 2.0,
            "reasoning": f"Mock evaluation: Candidate response lacks technical relevance to '{skill_tag}' and contains evasive or non-engineering content.",
            "red_flag": True,
            "needs_followup": False,
            "followup_question": None,
            "followup_reason": None,
            "eval_provider": "mock",
            "mock": True
        }

    domain_keywords = {
        "python": ["async", "await", "fastapi", "django", "event loop", "gil", "generator", "decorator", "pydantic", "sqlalchemy", "thread", "concurrency", "orm", "def", "class"],
        "backend": ["api", "rest", "endpoint", "database", "postgres", "sql", "cache", "redis", "latency", "throughput", "microservice", "index", "acid", "query"],
        "database": ["postgres", "index", "b-tree", "acid", "transaction", "foreign key", "normalization", "replica", "sharding", "pool", "query", "scan"],
        "frontend": ["react", "component", "hook", "useeffect", "usestate", "props", "typescript", "dom", "rendering", "bundle", "css", "layout"],
        "system": ["architecture", "scale", "load balancer", "cluster", "failover", "redundancy", "queue", "kafka", "event-driven", "cdn", "sharding"],
        "typescript": ["interface", "type", "generic", "compile", "static typing", "inference", "strict", "union", "enum"]
    }

    combined_targets = set(re.findall(r"\b\w{3,}\b", skill_tag.lower()) + re.findall(r"\b\w{4,}\b", question.lower()))
    for domain_key, terms in domain_keywords.items():
        if domain_key in skill_tag.lower() or domain_key in question.lower():
            combined_targets.update(terms)

    matched_keywords = [kw for kw in combined_targets if kw in cleaned]

    if len(matched_keywords) >= 3:
        score = 8.0
        reasoning = f"Mock evaluation: Answer contains strong domain concepts ({', '.join(matched_keywords[:4])}) matching '{skill_tag}' requirements."
        red_flag = False
    elif len(matched_keywords) >= 1:
        score = 5.5
        reasoning = f"Mock evaluation: Answer mentions basic terms ({', '.join(matched_keywords[:2])}) but lacks deeper implementation specifics for '{skill_tag}'."
        red_flag = False
    else:
        score = 4.0
        reasoning = f"Mock evaluation: Answer is grammatically structured but lacks targeted domain keywords for '{skill_tag}'."
        red_flag = False

    return {
        "score": score,
        "reasoning": reasoning,
        "red_flag": red_flag,
        "needs_followup": False,
        "followup_question": None,
        "followup_reason": None,
        "eval_provider": "mock",
        "mock": True
    }


def run_llm_evaluation(llm, question: str, skill_tag: str, answer_text: str, is_transcribed: bool = False) -> Dict[str, Any]:
    """Helper to execute evaluation prompt against a specific LLM instance with 1 retry on malformed/empty JSON."""
    asr_instruction = (
        "\n- ASR Noise Tolerance: Note: this answer was transcribed from spoken audio using automatic speech recognition, "
        "which can occasionally mangle technical proper nouns into similar-sounding but incorrect words (for example: 'Redis' "
        "becoming 'reads', 'asyncpg' becoming 'a sync page', 'aiohttp' becoming a garbled phrase). If a term appears nonsensical "
        "in context but a specific, well-known technical term would fit naturally and make the sentence coherent, assume the "
        "candidate said the correct term and evaluate their answer accordingly, rather than treating it as if the candidate "
        "used the wrong terminology. Be aware that Whisper commonly mistranscribes the HTTP method 'GET' as the word 'Git' "
        "(a version control tool) since they sound identical when spoken. If a transcribed answer mentions 'Git endpoint', "
        "'Git request', or similar phrasing in the context of API/REST/HTTP discussion, treat it as almost certainly meaning 'GET' "
        "and evaluate accordingly, unless the surrounding context clearly indicates the candidate is actually discussing the Git "
        "version control tool. However, if the surrounding explanation itself is vague, incorrect, or shows a genuine "
        "conceptual misunderstanding beyond just a single garbled word, still score that appropriately — this instruction is "
        "only about not penalizing ASR noise, not about being lenient on real technical errors.\n"
    ) if is_transcribed else ""

    prompt = (
        "You are an objective, rigorous senior technical interviewer evaluating a candidate's response and deciding on conversational follow-ups.\n"
        f"Skill Topic: {skill_tag}\n"
        f"Question: {question}\n"
        f"Candidate Answer: {answer_text}\n\n"
        "Evaluate the candidate's answer based on technical correctness, depth, practical clarity, and accuracy.\n"
        "Instructions:\n"
        "- Scoring Rubric (0 to 10):\n"
        "  * 9-10 = correct and demonstrates strong practical understanding of the core of the question; minor omissions of edge cases or advanced nuances should NOT prevent a 9 or 10 if the candidate clearly knows what they're doing.\n"
        "  * 7-8 = correct on the main point but with noticeable gaps in depth or missing an important consideration.\n"
        "  * 4-6 = partially correct, vague, or only superficially addresses the question.\n"
        "  * 1-3 = largely incorrect, misleading, or fails to address what was asked.\n"
        "  * 0 = no technical content at all, or completely off-topic.\n"
        "- Fairness & Conversational Phrasing: Grade the technical substance and reasoning, not polished grammar.\n"
        f"{asr_instruction}"
        "- Provide concise reasoning (2-3 sentences).\n"
        "- Set 'red_flag' to true if the candidate demonstrates fundamental misunderstandings, plagiarism-like buzzword spamming, dishonest claims, or scores 0-1 due to a total non-answer or complete topic mismatch, else false.\n\n"
        "- DYNAMIC COUNTER-QUESTION / FOLLOW-UP DECISION (Combined Single-Call):\n"
        "  * After evaluating the answer, decide whether a real technical interviewer would ask a natural follow-up or counter-question — for example, if the answer was vague, if it made a claim worth probing deeper on, if it skipped an important trade-off, or if there is an interesting technical angle worth challenging.\n"
        "  * Only set 'needs_followup' to true when a follow-up would genuinely add signal about the candidate's understanding — do not force one for every answer.\n"
        "  * If the answer was gibberish, off-topic, evasive, or already comprehensive and complete, set 'needs_followup' to false.\n"
        "  * When 'needs_followup' is true: 'followup_question' must be a short, natural, conversationally-phrased question that directly references what the candidate just said. Provide a 1-sentence 'followup_reason'.\n"
        "  * When 'needs_followup' is false: set 'followup_question' to null and 'followup_reason' to null.\n\n"
        "Return ONLY a valid JSON object in this format:\n"
        "{\n"
        "  \"score\": 8.5,\n"
        "  \"reasoning\": \"Clear explanation of core concepts with good real-world context.\",\n"
        "  \"red_flag\": false,\n"
        "  \"needs_followup\": true,\n"
        "  \"followup_question\": \"You mentioned using connection pooling with PostgreSQL, how would you handle pool exhaustion under high concurrent load?\",\n"
        "  \"followup_reason\": \"Probes candidate's understanding of database connection pool limits.\"\n"
        "}"
    )
    last_err = None
    for attempt in range(2):
        response = llm.invoke(prompt)
        raw_text = response.content if hasattr(response, 'content') else str(response)
        try:
            return clean_and_parse_json(raw_text)
        except Exception as e:
            last_err = e
            logger.warning(
                f"[EVAL] JSON parse error on attempt {attempt + 1}/2. Raw response: {repr(raw_text)}. Error: {e}"
            )
            if attempt == 0:
                logger.info("[EVAL] Retrying evaluation call with same prompt...")

    raise last_err or ValueError("Failed to parse valid JSON from evaluation LLM response.")


def evaluate_answer(question: str, skill_tag: str, answer_text: str, is_transcribed: bool = False) -> Dict[str, Any]:
    """Evaluates candidate response via Fallback Chain: Groq -> Ollama -> Heuristic Mock."""
    cleaned = (answer_text or "").strip()
    if len(cleaned) < 5 or cleaned.lower() in ["idk", "dont know", "no idea", "asdf", "test"]:
        return {
            "score": 0.0,
            "reasoning": "Answer is evasive, empty, or lacks meaningful technical substance.",
            "red_flag": True,
            "needs_followup": False,
            "followup_question": None,
            "followup_reason": None,
            "eval_provider": "rule_check",
            "mock": False
        }

    # Tier 1: Try Primary Provider (Groq: openai/gpt-oss-120b)
    groq_llm = create_llm_client(provider=settings.EVAL_MODEL_PROVIDER, model_name=settings.EVAL_MODEL_NAME, temperature=0.2)
    if groq_llm:
        try:
            parsed = run_llm_evaluation(groq_llm, question, skill_tag, cleaned, is_transcribed=is_transcribed)
            score = float(parsed.get("score", 5.0))
            red_flag = bool(parsed.get("red_flag", False))
            # Ensure 0-1 scores due to non-answers/topic mismatches trigger red_flag
            if score <= 1.0:
                red_flag = True

            needs_followup = bool(parsed.get("needs_followup", False))
            followup_question = parsed.get("followup_question") if needs_followup else None
            followup_reason = parsed.get("followup_reason") if needs_followup else None

            logger.info(f"[EVAL] Used: {settings.EVAL_MODEL_PROVIDER} ({settings.EVAL_MODEL_NAME}) - Needs Follow-up: {needs_followup}")
            return {
                "score": score,
                "reasoning": str(parsed.get("reasoning", "Answer evaluated.")),
                "red_flag": red_flag,
                "needs_followup": needs_followup,
                "followup_question": str(followup_question).strip() if followup_question else None,
                "followup_reason": str(followup_reason).strip() if followup_reason else None,
                "eval_provider": "groq",
                "mock": False
            }
        except Exception as e:
            if "model_not_found" in str(e).lower() or "404" in str(e):
                logger.warning(f"[EVAL] Groq model '{settings.EVAL_MODEL_NAME}' not found or deprecated (see https://console.groq.com/docs/deprecations). Falling back to ollama ({settings.EVAL_FALLBACK_MODEL_NAME}).")
            else:
                logger.warning(f"[EVAL] Groq failed ({e}), falling back to ollama ({settings.EVAL_FALLBACK_MODEL_NAME})")
    else:
        logger.warning(f"[EVAL] Groq not configured, falling back to ollama ({settings.EVAL_FALLBACK_MODEL_NAME})")

    # Tier 2: Try Fallback Provider (Ollama: qwen2.5:7b)
    ollama_llm = create_llm_client(provider=settings.EVAL_FALLBACK_MODEL_PROVIDER, model_name=settings.EVAL_FALLBACK_MODEL_NAME, temperature=0.2)
    if ollama_llm:
        try:
            parsed = run_llm_evaluation(ollama_llm, question, skill_tag, cleaned, is_transcribed=is_transcribed)
            score = float(parsed.get("score", 5.0))
            red_flag = bool(parsed.get("red_flag", False))
            if score <= 1.0:
                red_flag = True

            needs_followup = bool(parsed.get("needs_followup", False))
            followup_question = parsed.get("followup_question") if needs_followup else None
            followup_reason = parsed.get("followup_reason") if needs_followup else None

            logger.info(f"[EVAL] Used: ollama_fallback ({settings.EVAL_FALLBACK_MODEL_NAME}) - Needs Follow-up: {needs_followup}")
            return {
                "score": score,
                "reasoning": str(parsed.get("reasoning", "Answer evaluated.")),
                "red_flag": red_flag,
                "needs_followup": needs_followup,
                "followup_question": str(followup_question).strip() if followup_question else None,
                "followup_reason": str(followup_reason).strip() if followup_reason else None,
                "eval_provider": "ollama_fallback",
                "mock": False
            }
        except Exception as e:
            logger.warning(f"[EVAL] Ollama fallback failed ({e}), falling back to heuristic mock")

    # Tier 3: Final Safety Net - Heuristic Mock
    logger.warning("[EVAL] Ollama unavailable, falling back to heuristic mock")
    return evaluate_answer_mock_heuristic(question, skill_tag, answer_text)


# --- 5. Generate Summary Report Chain with Fallback Chain (Groq -> Ollama -> Mock) ---
def run_llm_summary(llm, candidate_name: str, overall_score: float, transcript_summary: str) -> Dict[str, Any]:
    """Helper to execute summary prompt against a specific LLM instance with 1 retry on malformed/empty JSON."""
    prompt = (
        "You are an executive hiring bar raiser and senior engineering director.\n"
        f"Review the full interview transcript and evaluation scores for candidate '{candidate_name}'.\n"
        f"Overall Computed Weighted Score: {overall_score}/10.\n"
        f"Full Transcript & Turn Evaluations:\n{transcript_summary}\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. If the candidate had poor scores or little skill overlap, you MUST state low fit honestly rather than defaulting to a positive recommendation.\n"
        "2. Provide an objective executive summary paragraph (3-4 sentences).\n"
        "3. List 2-4 key candidate strengths demonstrated in their answers.\n"
        "4. List 2-4 key candidate weaknesses or areas for improvement.\n"
        "5. Final hiring recommendation MUST be strictly one of: 'pass', 'fail', or 'borderline'.\n"
        "   - 'pass': Strong technical competency, score >= 7.0, no severe red flags.\n"
        "   - 'borderline': Mixed performance (5.0 - 6.9), some knowledge gaps.\n"
        "   - 'fail': Score < 5.0, frequent red flags, or severe lack of competence.\n\n"
        "Return ONLY a valid JSON object in this format:\n"
        "{\n"
        "  \"summary\": \"Executive summary text...\",\n"
        "  \"strengths\": [\"Strength 1\", \"Strength 2\"],\n"
        "  \"weaknesses\": [\"Weakness 1\", \"Weakness 2\"],\n"
        "  \"recommendation\": \"pass\"\n"
        "}"
    )
    last_err = None
    for attempt in range(2):
        response = llm.invoke(prompt)
        raw_text = response.content if hasattr(response, 'content') else str(response)
        try:
            parsed = clean_and_parse_json(raw_text)
            rec = str(parsed.get("recommendation", "borderline")).lower().strip()
            if rec not in ["pass", "fail", "borderline"]:
                rec = "borderline"
            return {
                "summary": str(parsed.get("summary", "Interview completed.")),
                "strengths": list(parsed.get("strengths", ["Demonstrated core technical competencies"])),
                "weaknesses": list(parsed.get("weaknesses", ["Further depth required in advanced topics"])),
                "recommendation": rec
            }
        except Exception as e:
            last_err = e
            logger.warning(
                f"[EVAL] Summary JSON parse error on attempt {attempt + 1}/2. Raw response: {repr(raw_text)}. Error: {e}"
            )
            if attempt == 0:
                logger.info("[EVAL] Retrying summary call with same prompt...")

    raise last_err or ValueError("Failed to parse valid JSON from summary LLM response.")


def generate_summary(session_data: Dict[str, Any]) -> Dict[str, Any]:
    """Synthesizes executive report via Fallback Chain: Groq -> Ollama -> Heuristic Mock."""
    transcript_summary = json.dumps(session_data.get("transcript", []))
    overall_score = session_data.get("overall_score", 0.0)
    candidate_name = session_data.get("candidate_name", "Candidate")

    # Tier 1: Try Primary Provider (Groq: llama-3.3-70b-versatile)
    groq_llm = create_llm_client(provider=settings.EVAL_MODEL_PROVIDER, model_name=settings.EVAL_MODEL_NAME, temperature=0.2)
    if groq_llm:
        try:
            res = run_llm_summary(groq_llm, candidate_name, overall_score, transcript_summary)
            logger.info(f"[EVAL] Summary generated via: {settings.EVAL_MODEL_PROVIDER} ({settings.EVAL_MODEL_NAME})")
            res["eval_provider"] = "groq"
            res["mock"] = False
            return res
        except Exception as e:
            if "model_not_found" in str(e).lower() or "404" in str(e):
                logger.warning(f"[EVAL] Groq summary model '{settings.EVAL_MODEL_NAME}' not found or deprecated (see https://console.groq.com/docs/deprecations). Falling back to ollama ({settings.EVAL_FALLBACK_MODEL_NAME}).")
            else:
                logger.warning(f"[EVAL] Groq summary failed ({e}), falling back to ollama ({settings.EVAL_FALLBACK_MODEL_NAME})")
    else:
        logger.warning(f"[EVAL] Groq not configured for summary, falling back to ollama ({settings.EVAL_FALLBACK_MODEL_NAME})")

    # Tier 2: Try Fallback Provider (Ollama: qwen2.5:7b)
    ollama_llm = create_llm_client(provider=settings.EVAL_FALLBACK_MODEL_PROVIDER, model_name=settings.EVAL_FALLBACK_MODEL_NAME, temperature=0.2)
    if ollama_llm:
        try:
            res = run_llm_summary(ollama_llm, candidate_name, overall_score, transcript_summary)
            logger.info(f"[EVAL] Summary generated via: ollama_fallback ({settings.EVAL_FALLBACK_MODEL_NAME})")
            res["eval_provider"] = "ollama_fallback"
            res["mock"] = False
            return res
        except Exception as e:
            logger.warning(f"[EVAL] Ollama summary failed ({e}), falling back to mock summary")

    # Tier 3: Final Safety Net - Heuristic Mock Summary
    logger.warning("[EVAL] Ollama unavailable, falling back to heuristic mock summary")
    rec = "pass" if overall_score >= 7.0 else ("borderline" if overall_score >= 5.0 else "fail")
    return {
        "summary": f"Evaluation summary for {candidate_name}. Candidate achieved an overall score of {overall_score}/10.",
        "strengths": ["Demonstrated key technical responses", "Structured explanations on primary topics"],
        "weaknesses": ["Further architecture depth recommended in complex scenarios"],
        "recommendation": rec,
        "eval_provider": "mock",
        "mock": True
    }
