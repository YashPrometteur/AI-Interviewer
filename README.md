# AI Interviewer - Phase 1

Automated AI Interviewer MVP supporting candidate resume & JD parsing, adaptive question bank generation, turn-based answer scoring, and candidate hiring report synthesis.

---

## Database Architecture (MongoDB)
- **Database**: MongoDB (`ai_interviewer` database)
- **Driver**: PyMongo (synchronous)
- **Document Structure**: Single canonical `sessions` collection with embedded candidate metadata, nested question bank array with in-place turn answers, and final executive report.
- **Config**: `MONGODB_URL=mongodb://localhost:27017`, `DATABASE_NAME=ai_interviewer` (configured in `backend/.env`)

---

## Model Routing Architecture

### 1. Fast Generation (JD Skills & Question Generation)
- **Provider**: `ollama`
- **Model**: `qwen2.5:7b`
- **Config**: `GENERATION_MODEL_PROVIDER=ollama`, `GENERATION_MODEL_NAME=qwen2.5:7b`

### 2. High-Stakes Answer Evaluation & Report Summary (3-Tier Fallback Chain)
- **Tier 1 (Primary)**: Groq (`openai/gpt-oss-20b`)
  - Config: `EVAL_MODEL_PROVIDER=groq`, `EVAL_MODEL_NAME=openai/gpt-oss-20b`
- **Tier 2 (Fallback)**: Local Ollama (`qwen2.5:7b`)
  - Config: `EVAL_FALLBACK_MODEL_PROVIDER=ollama`, `EVAL_FALLBACK_MODEL_NAME=qwen2.5:7b`
  - Triggered automatically on any Groq failure (429 rate limit, quota exhaustion, timeout, connection drop).
- **Tier 3 (Safety Net)**: Keyword-aware heuristic mock evaluator (used only if both Groq and local Ollama are offline).

Every answer evaluation and final report in the database is tagged with its `eval_provider` (`"groq" | "ollama_fallback" | "mock"`).

---

## Important: Groq Model Deprecations

Groq periodically deprecates and renames model identifiers. If evaluations or summaries ever fail with `model_not_found` or HTTP 404:
1. Check the official Groq deprecations reference: [Groq Model Deprecations](https://console.groq.com/docs/deprecations).
2. Update `EVAL_MODEL_NAME` in `backend/.env` with the current recommended model identifier.
3. The system's automatic fallback chain will route evaluations to Ollama or the safety mock in the meantime without crashing the application.
