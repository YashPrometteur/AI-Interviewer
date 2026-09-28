# Phase 1: AI Interviewer - Architectural & Technical Walkthrough

A comprehensive, code-level guide explaining how the text-based AI Interviewer MVP works end-to-end. This document is written from first principles to explain the exact mechanics, algorithms, and design choices implemented across the backend.

---

## 1. High-Level Flow

The Phase 1 lifecycle spans three distinct stages: **Session Initialization & Question Bank Generation**, **Adaptive Turn-by-Turn Interview Flow**, and **Session Finalization & Executive Synthesis**.

```text
[ Recruiter / Candidate ]
            │
            ▼  (POST /api/sessions: JD + Resume)
┌───────────────────────────────────────────────────────────┐
│ 1. router.create_interview_session()                      │
│    └─► service.start_session()                            │
│         ├─► parser.parse_resume()                         │
│         ├─► parser.extract_skills_from_jd() (Ollama)      │
│         ├─► parser.extract_candidate_background() (Ollama)│
│         ├─► chains.generate_questions() (Ollama 3x/skill) │
│         └─► db.sessions.insert_one(build_session_doc)     │
└───────────────────────────────────────────────────────────┘
            │
            ▼  (GET /api/sessions/{id}/next-question)
┌───────────────────────────────────────────────────────────┐
│ 2. router.get_next_question_endpoint()                    │
│    └─► service.get_next_question()                        │
│         ├─► Read unanswered embedded questions            │
│         ├─► scoring.determine_difficulty_progression()    │
│         └─► Return selected QuestionOut (easy/med/hard)   │
└───────────────────────────────────────────────────────────┘
            │
            ▼  (POST /api/sessions/{id}/answer)
┌───────────────────────────────────────────────────────────┐
│ 3. router.submit_answer_endpoint()                        │
│    └─► service.submit_answer()                            │
│         ├─► chains.evaluate_answer()                      │
│         │    ├─► Tier 1: Groq (openai/gpt-oss-20b)        │
│         │    ├─► Tier 2: Ollama (qwen2.5:7b) [on error]   │
│         │    └─► Tier 3: Heuristic Mock [safety net]      │
│         └─► db.sessions.update_one(questions.$.answer)    │
└───────────────────────────────────────────────────────────┘
            │
            ▼  (POST /api/sessions/{id}/complete)
┌───────────────────────────────────────────────────────────┐
│ 4. router.complete_session_endpoint()                     │
│    └─► service.complete_session()                         │
│         ├─► scoring.compute_weighted_score()              │
│         ├─► chains.generate_summary() (Groq -> Ollama)    │
│         └─► db.sessions.update_one(report, completed)     │
└───────────────────────────────────────────────────────────┘
            │
            ▼  (GET /api/reports/{id})
┌───────────────────────────────────────────────────────────┐
│ 5. router.get_report_endpoint()                           │
│    └─► reports_service.get_full_report()                  │
│         └─► Returns FullReportResponse + Transcript       │
└───────────────────────────────────────────────────────────┘
```

---

## 2. File-by-File Breakdown

### `backend/app/core/config.py`
- **Responsibility**: Centralized configuration management using `pydantic-settings`. Loads environment variables from `.env` using absolute path resolution.
- **Key Fields**:
  - `MONGODB_URL`: Connection string (default: `"mongodb://localhost:27017"`).
  - `DATABASE_NAME`: Target database (default: `"ai_interviewer"`).
  - `GENERATION_MODEL_PROVIDER` (`"ollama"`) & `GENERATION_MODEL_NAME` (`"qwen2.5:7b"`).
  - `EVAL_MODEL_PROVIDER` (`"groq"`) & `EVAL_MODEL_NAME` (`"openai/gpt-oss-20b"`).
  - `EVAL_FALLBACK_MODEL_PROVIDER` (`"ollama"`) & `EVAL_FALLBACK_MODEL_NAME` (`"qwen2.5:7b"`).
  - `OLLAMA_BASE_URL`: Endpoint for local daemon (default: `"http://localhost:11434"`).
- **Dependencies**: Loaded by `database.py`, `chains.py`, and `service.py`.

### `backend/app/core/utils.py`
- **Responsibility**: Raw text extraction and safety sanitization.
- **Key Functions**:
  - `extract_text_from_file_bytes(content: bytes, filename: str) -> str`: Uses `pypdf` for `.pdf` and `python-docx` for `.docx`, with fallback to utf-8/latin-1 string decoding.
  - `sanitize_and_truncate_text(text: str, max_chars=15000) -> str`: Strips whitespace and enforces context window safety limits.
- **Dependencies**: Used by `parser.py`.

### `backend/app/db/database.py`
- **Responsibility**: MongoDB database connection manager.
- **Key Components**:
  - `client: MongoClient`: Global singleton connection instance.
  - `database: Database`: Active database handle.
  - `get_db() -> Database`: FastAPI dependency injected via `Depends(get_db)`.
- **Dependencies**: Injected into `interview/router.py` and `reports/router.py`.

### `backend/app/db/models.py`
- **Responsibility**: Canonical builder functions for MongoDB embedded documents.
- **Key Functions**:
  - `build_session_document(...)`: Top-level session dictionary.
  - `build_candidate_entry(...)`: Embedded candidate metadata subdocument.
  - `build_question_entry(...)`: Embedded question object with a unique UUID and initial `answer: None`.
  - `build_answer_entry(...)`: Embedded answer object with score, reasoning, and evaluation tier tag.
  - `build_report_entry(...)`: Embedded executive scorecard summary.
- **Dependencies**: Imported by `interview/service.py`.

### `backend/app/db/schemas.py`
- **Responsibility**: Pydantic models for HTTP request validation and JSON API responses.
- **Key Schemas**:
  - `SessionCreateResponse`: Initial session metadata and generated question count.
  - `QuestionOut`: Question delivered to the frontend (`id`, `text`, `skill_tag`, `difficulty`).
  - `AnswerSubmitRequest`: Payload containing candidate's typed answer.
  - `AnswerEvaluationOut`: Evaluation feedback returned after each turn.
  - `CompleteSessionResponse` & `FullReportResponse`: Comprehensive executive reports with full transcript.
- **Dependencies**: Used by FastAPI routers and service functions.

### `backend/app/interview/parser.py`
- **Responsibility**: High-level parsing pipeline connecting file bytes and raw text to AI prompt chains.
- **Key Functions**:
  - `parse_resume(file_content, filename)`: Extracts and cleans resume text.
  - `extract_skills_from_jd(jd_text)`: Calls `extract_skills_chain`.
  - `extract_candidate_background(resume_text, jd_skills)`: Calls `extract_background_chain`.
- **Dependencies**: Called by `interview/service.py`.

### `backend/app/ai/chains.py`
- **Responsibility**: LangChain prompt construction, model provider instantiation (Groq/Ollama), JSON extraction, and 3-tier evaluation fallback execution.
- **Key Functions**:
  - `extract_skills_chain(jd_text)` (Ollama)
  - `extract_background_chain(resume_text, jd_skills)` (Ollama)
  - `generate_questions(jd_skills, resume_summary)` (Ollama)
  - `evaluate_answer(question, skill_tag, answer_text)` (Groq -> Ollama -> Mock)
  - `generate_summary(session_data)` (Groq -> Ollama -> Mock)
- **Dependencies**: Called by `parser.py` and `service.py`.

### `backend/app/ai/scoring.py`
- **Responsibility**: Pure deterministic mathematical calculations for weighted skill scores and adaptive difficulty progression.
- **Key Functions**:
  - `compute_weighted_score(answers_data, skill_weights)`: Re-normalized skill-weighted average.
  - `determine_difficulty_progression(last_score, current_difficulty)`: Easy/Medium/Hard progression state machine.
- **Dependencies**: Called by `interview/service.py`.

### `backend/app/interview/service.py`
- **Responsibility**: Main business logic orchestrator for the interview lifecycle against MongoDB.
- **Key Functions**:
  - `start_session`: Validates input, triggers question bank generation, and inserts the session document into MongoDB.
  - `get_next_question`: Finds the next unanswered question based on performance-driven difficulty progression.
  - `submit_answer`: Runs AI evaluation and atomically updates the embedded question via the positional `$set` operator.
  - `complete_session`: Computes weighted score, synthesizes the executive report, and marks the session completed.
  - `list_sessions`: Lightweight projection query for recruiter monitoring.
- **Dependencies**: Invoked by `interview/router.py`.

### `backend/app/interview/router.py` & `backend/app/reports/router.py`
- **Responsibility**: FastAPI HTTP route declarations. Injects `db: Database = Depends(get_db)` and translates HTTP multipart/JSON bodies into service calls.

### `backend/app/reports/service.py`
- **Responsibility**: Compiles the complete candidate scorecard, transcript, and AI summary from the MongoDB session document.

---

## 3. The AI Part — Deep Technical Explanation

### a) Do We Use RAG or Embeddings/FAISS in Phase 1?
**No. There is zero RAG, vector search, or embedding calculation (FAISS/Chroma) in Phase 1.**

**What is done instead**: Raw Job Description text and parsed resume text are sanitized and passed **directly as formatted prompt strings** into the LLM context window.

**Why this is sufficient**:
- A typical Job Description is 300–800 words (~1,000–3,000 tokens).
- A typical 2-page resume is 600–1,500 words (~2,000–4,000 tokens).
- Modern LLMs (e.g. `qwen2.5:7b` with 32k context, or `gpt-oss-20b` with 8k–128k context) easily accommodate both documents simultaneously in a single prompt without chunking or vector retrieval.
- Direct prompt injection provides full holistic document context without retrieval loss or chunk boundary issues.

---

### b) Detailed Breakdown of the 5 AI Functions (`chains.py`)

#### 1. `extract_skills_chain(jd_text: str)`
- **Role**: Analyzes the JD to extract 3–5 core competencies and assigns normalized importance weights summing strictly to 1.0.
- **Model**: **Ollama (`qwen2.5:7b`)** — Fast, local, zero API cost.
- **Prompt**:
  ```text
  You are an expert technical recruiter and hiring architect.
  Analyze the following Job Description (JD) and extract the top 3-5 distinct required skills or technical competencies.
  Assign an importance weight to each skill such that the sum of all weights strictly equals 1.0.
  
  Job Description:
  {jd_text}
  
  Return ONLY a valid JSON array in this exact schema:
  [
    {"skill": "Python Backend", "weight": 0.4},
    {"skill": "Database & SQL", "weight": 0.3},
    {"skill": "System Architecture", "weight": 0.3}
  ]
  ```
- **Output Shape**:
  ```python
  {
      "skills": [{"skill": str, "weight": float}],
      "mock": bool
  }
  ```

#### 2. `extract_candidate_background(resume_text: str, skills: List[Dict])`
- **Role**: Summarizes the candidate's actual experience for each extracted skill from their resume.
- **Model**: **Ollama (`qwen2.5:7b`)**.
- **Prompt**:
  ```text
  You are an expert technical recruiter reviewing a candidate's resume.
  For each required skill below, extract and summarize the candidate's relevant background and depth from their resume.
  
  Skills to evaluate: {json.dumps(skill_names)}
  Candidate Resume:
  {resume_text}
  
  Return ONLY a valid JSON object mapping each skill name to a 1-2 sentence summary of experience.
  ```
- **Output Shape**:
  ```python
  {
      "background": {"Skill Name": "Summary string..."},
      "mock": bool
  }
  ```

#### 3. `generate_questions(jd_skills, resume_summary)`
- **Role**: Creates the entire question bank upfront: exactly 3 progressive questions per skill (1 easy, 1 medium, 1 hard).
- **Model**: **Ollama (`qwen2.5:7b`)**.
- **Prompt**:
  ```text
  You are an expert technical interviewer designing an interview question bank.
  For each skill listed in the requirements, generate EXACTLY 3 progressive questions tailored to the candidate's background:
  - 1 'easy' question (fundamentals, core definitions, basic usage)
  - 1 'medium' question (practical scenario, debugging, API design, trade-offs)
  - 1 'hard' question (system design, scalability, edge cases, failure modes)
  
  Skills & Weights: {json.dumps(jd_skills)}
  Candidate Background Summary: {json.dumps(resume_summary)}
  
  Return ONLY a valid JSON array of question objects:
  [
    {"text": "...", "skill_tag": "Skill Name", "difficulty": "easy"},
    {"text": "...", "skill_tag": "Skill Name", "difficulty": "medium"},
    {"text": "...", "skill_tag": "Skill Name", "difficulty": "hard"}
  ]
  ```
- **Output Shape**:
  ```python
  {
      "questions": [{"text": str, "skill_tag": str, "difficulty": str}],
      "mock": bool
  }
  ```

#### 4. `evaluate_answer(question, skill_tag, answer_text)`
- **Role**: High-stakes evaluation of a candidate's answer on correctness, depth, practical understanding, and dishonesty.
- **Model Routing**: **3-Tier Fallback Chain (Groq `openai/gpt-oss-20b` -> Ollama `qwen2.5:7b` -> Heuristic Mock)**.
- **Prompt (`run_llm_evaluation`)**:
  ```text
  You are an objective, rigorous senior technical interviewer evaluating a candidate's response.
  Skill Topic: {skill_tag}
  Question: {question}
  Candidate Answer: {answer_text}
  
  Evaluate the candidate's answer based on technical correctness, depth, practical clarity, and accuracy.
  Instructions:
  - Score from 0 to 10 (10 = exceptional & comprehensive, 7-8 = solid/correct, 4-6 = partial/vague, 0-3 = incorrect or misleading).
  - Provide concise reasoning (2-3 sentences).
  - Set 'red_flag' to true if the candidate demonstrates fundamental misunderstandings, plagiarism-like buzzword spamming, or dishonest claims, else false.
  
  Return ONLY a valid JSON object:
  {
    "score": 8.5,
    "reasoning": "...",
    "red_flag": false
  }
  ```
- **Output Shape**:
  ```python
  {
      "score": float,
      "reasoning": str,
      "red_flag": bool,
      "eval_provider": "groq" | "ollama_fallback" | "mock" | "rule_check",
      "mock": bool
  }
  ```

#### 5. `generate_summary(session_data)`
- **Role**: Executive synthesis of full interview transcript and overall weighted score.
- **Model Routing**: **3-Tier Fallback Chain (Groq -> Ollama -> Heuristic Mock)**.
- **Prompt (`run_llm_summary`)**:
  ```text
  You are an executive hiring bar raiser and senior engineering director.
  Review the full interview transcript and evaluation scores for candidate '{candidate_name}'.
  Overall Computed Weighted Score: {overall_score}/10.
  Full Transcript & Turn Evaluations:
  {transcript_summary}
  
  CRITICAL INSTRUCTIONS:
  1. If the candidate had poor scores or little skill overlap, you MUST state low fit honestly rather than defaulting to a positive recommendation.
  2. Provide an objective executive summary paragraph (3-4 sentences).
  3. List 2-4 key candidate strengths demonstrated in their answers.
  4. List 2-4 key candidate weaknesses or areas for improvement.
  5. Final hiring recommendation MUST be strictly one of: 'pass', 'fail', or 'borderline'.
     - 'pass': Strong technical competency, score >= 7.0, no severe red flags.
     - 'borderline': Mixed performance (5.0 - 6.9), some knowledge gaps.
     - 'fail': Score < 5.0, frequent red flags, or severe lack of competence.
  
  Return ONLY a valid JSON object:
  {
    "summary": "...",
    "strengths": ["...", "..."],
    "weaknesses": ["...", "..."],
    "recommendation": "pass"
  }
  ```

---

### c) JSON Parsing & Resilience Pipeline

When LLMs return Markdown code blocks (` ```json ... ``` `) or conversational surrounding prose, `clean_and_parse_json()` handles extraction:
1. Strips outer whitespace.
2. Checks for markdown triple backticks with regex `r"```(?:json)?\s*([\s\S]*?)\s*```"`.
3. If bare `json.loads()` fails with a `JSONDecodeError`, attempts regex extraction of outermost curly brackets `{...}` or square brackets `[...]`.
4. **Retry on Parse Failure**: Both `run_llm_evaluation` and `run_llm_summary` execute an automatic retry loop (up to 2 attempts). If Attempt 1 returns malformed or empty text, it logs the raw output at `WARNING` level and retries the exact prompt once before triggering fallback.

---

### d) How Question Generation & Bank Sizing Works
1. `extract_skills_from_jd` extracts $N$ skills (usually 3 to 4 skills).
2. `generate_questions` creates **exactly 3 progressive questions per skill**:
   $$\text{Total Questions} = N \times 3$$
   *(e.g., 3 skills $\times$ 3 = 9 questions total).*
3. Each skill has 1 Easy, 1 Medium, and 1 Hard question stored upfront in the `questions` array inside the MongoDB session document.
4. **Why generate upfront?**
   - Single generation LLM call rather than making LLM calls before every turn.
   - Allows instant question delivery (`GET /next-question`) with zero candidate latency during the interview.

---

### e) How Adaptive Difficulty Progression Works at Runtime

In `backend/app/ai/scoring.py` (`determine_difficulty_progression`):
```python
def determine_difficulty_progression(last_score: float, current_difficulty: str = "medium") -> str:
    levels = ["easy", "medium", "hard"]
    curr_idx = levels.index(current_difficulty)
    
    if last_score >= 7.0:
        next_idx = min(2, curr_idx + 1)   # Promote difficulty
    elif last_score <= 3.0:
        next_idx = max(0, curr_idx - 1)   # Demote difficulty
    else:
        next_idx = curr_idx               # Maintain difficulty
        
    return levels[next_idx]
```

**Runtime Call Flow (`service.get_next_question`)**:
1. Checks the last answered question's score and difficulty from `session["questions"]`.
2. Computes `target_difficulty` (e.g. candidate scored $8.5/10$ on a Medium question $\rightarrow$ target becomes `hard`).
3. Selects the first unanswered question matching `hard`.
4. If no unanswered `hard` questions remain, it falls back to the next available unanswered question in the bank.

---

### f) The 3-Tier Model Fallback System

Implemented in `chains.evaluate_answer()` and `chains.generate_summary()`:

```text
[ Incoming Answer / Summary Request ]
                  │
                  ▼
         ┌──────────────────┐
         │ Tier 1: Groq     │ ──► Success: tag eval_provider = "groq"
         │ (gpt-oss-20b)    │
         └──────────────────┘
                  │ (Fails: 429, Quota, 404 Deprecation, Timeout, Malformed JSON)
                  ▼
         ┌──────────────────┐
         │ Tier 2: Ollama   │ ──► Success: tag eval_provider = "ollama_fallback"
         │ (qwen2.5:7b)     │
         └──────────────────┘
                  │ (Fails: Daemon offline, socket timeout)
                  ▼
         ┌──────────────────┐
         │ Tier 3: Heuristic│ ──► Success: tag eval_provider = "mock"
         │ Safety Mock      │
         └──────────────────┘
```

- **Failure Detection**:
  - Socket reachability check (`is_ollama_reachable`) checks port 11434 in $<0.3\text{s}$ before initializing Ollama.
  - Python `try...except Exception` catches HTTP errors, rate limit exceptions, deprecation 404s, and parse errors.
- **Provider Tagging**:
  - The resulting `eval_provider` (`"groq"`, `"ollama_fallback"`, or `"mock"`) is persisted directly onto the embedded `Answer` and `Report` in MongoDB.
  - Recruiter dashboards and candidate scorecards can clearly verify whether a score came from the high-tier cloud LLM or a fallback model.

---

### g) Weighted Scoring Math with Concrete Example

Implemented in `backend/app/ai/scoring.py` (`compute_weighted_score`):

#### Mathematical Formula
$$\text{Overall Score} = \sum_{i=1}^{K} \left( \overline{S_i} \times \frac{W_i}{\sum_{j=1}^{K} W_j} \right)$$
Where:
- $\overline{S_i}$ is the average score for skill $i$.
- $W_i$ is the importance weight of skill $i$.
- The denominator $\sum W_j$ re-normalizes weights across only the skills that were actually evaluated (handling cases where an interview ended early).

#### Concrete Example (Alex Rivera - Python Senior Backend)
- **Extracted Skills & Weights**:
  - Skill A: **Python Backend** ($W_1 = 0.40$)
  - Skill B: **Database & SQL** ($W_2 = 0.35$)
  - Skill C: **System Architecture** ($W_3 = 0.25$)

- **Candidate Scores**:
  - Python Backend: Question 1 Score = `8.5`, Question 2 Score = `9.0` $\rightarrow \overline{S_1} = 8.75$
  - Database & SQL: Question 3 Score = `8.0` $\rightarrow \overline{S_2} = 8.00$
  - System Architecture: Question 4 Score = `7.0` $\rightarrow \overline{S_3} = 7.00$

- **Calculation**:
  $$\text{Score} = (8.75 \times 0.40) + (8.00 \times 0.35) + (7.00 \times 0.25)$$
  $$\text{Score} = 3.50 + 2.80 + 1.75 = 8.05 \approx \mathbf{8.1 / 10}$$

---

## 4. Prompt Engineering Decisions

1. **Strict JSON Schema Enforcement**:
   All prompts specify `Return ONLY a valid JSON object/array... with no additional text or markdown`. This minimizes conversational filler (e.g. *"Here is your evaluation:"*) and optimizes parse reliability.
2. **Deterministic Temperature Tuning**:
   - `temperature = 0.2` for evaluation and scoring (high consistency, objective grading).
   - `temperature = 0.3` for skill extraction and question generation (slight variety while preserving strict schema adherance).
3. **Single-Shot Chains vs. Agent Loops**:
   Evaluation does not use multi-step agent reasoning loops (like ReAct). Single-prompt zero-shot judging executes in $<1.5\text{s}$ per turn, providing fast candidate interaction.
4. **Hiring Bar Calibrations**:
   Prompts explicitly instruct the LLM: *"If the candidate had poor scores or little skill overlap, you MUST state low fit honestly rather than defaulting to a positive recommendation."* This prevents generic "polite pass" inflation.

---

## 5. What’s Not Yet Built & Roadmap to Future Phases

| Feature / Area | Phase 1 Status | Future Plan (Phase 2 & 3) |
| :--- | :--- | :--- |
| **Media Modality** | Text-only (candidate types in browser) | **Phase 2**: Audio/Video STT (Whisper) & TTS with WebRTC streaming. |
| **RAG / Vector DB** | Direct prompt injection | Will be added if supporting long 50-page enterprise portfolios or cross-candidate historical matching. |
| **Proctoring & Integrity** | Simple rule checks (empty/spam flags) | **Phase 3**: Face detection, multi-person alerts, tab-switch tracking, and integrity score index. |
| **Candidate Reusability** | Embedded directly in session doc | Separate collection if candidates apply to multiple job openings. |

---

## 6. Glossary of Terms

- **Embedded Document**: Storing related data (questions, answers, reports) inside a single parent MongoDB document rather than joining flat relational tables.
- **Fallback Chain**: A multi-tiered failover strategy (Groq $\rightarrow$ Ollama $\rightarrow$ Heuristic Mock) ensuring high availability.
- **Difficulty Progression**: Dynamically adapting the challenge level of upcoming questions based on candidate performance on preceding questions.
- **Weighted Scoring**: Combining multiple skill ratings into a single score using importance weights defined by the job description.
- **`eval_provider` Tagging**: An audit metadata tag recorded on every score indicating whether Groq, Ollama, or a safety fallback evaluated the answer.
- **Structured Output**: Forcing LLMs to respond strictly in machine-readable JSON format matching Pydantic schemas.
