"""Standalone Rubric Ceiling Verification Script.

Tests evaluate_answer() using hand-written, clean, genuinely correct answers
(without relying on Ollama question/answer generation) to measure whether strong answers
reach the 9-10 score range under the updated rubric with openai/gpt-oss-120b on Groq.
"""
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.ai.chains import evaluate_answer

TEST_CASES = [
    {
        "id": 1,
        "skill_tag": "FastAPI & Backend Performance",
        "question": "How would you implement rate limiting in a FastAPI application?",
        "answer": (
            "I'd use a dependency-based approach with FastAPI's Depends mechanism, combined "
            "with Redis to track request counts per client — typically keyed by IP address or an API "
            "token. A sliding window or token bucket algorithm works well here. Redis is a good fit "
            "because it's fast and supports atomic increment operations, which avoids race conditions "
            "when multiple requests hit the counter at once. I'd return a 429 status code with a "
            "Retry-After header when a client exceeds their limit."
        )
    },
    {
        "id": 2,
        "skill_tag": "Python Core Fundamentals",
        "question": "Explain the difference between mutable and immutable objects in Python.",
        "answer": (
            "Mutable objects, like lists, dicts, and sets, can be changed in place after "
            "creation — you can append to a list without creating a new object. Immutable objects, "
            "like strings, tuples, and ints, can't be changed once created; any 'modification' "
            "actually creates a new object in memory. This matters for things like function default "
            "arguments — using a mutable default like a list can cause bugs because it's shared across "
            "calls, which is a classic Python gotcha. I use tuples over lists when I want to guarantee "
            "the data won't be accidentally modified, like for fixed configuration values."
        )
    },
    {
        "id": 3,
        "skill_tag": "SQL & Relational Databases",
        "question": "Explain the difference between an INNER JOIN and a LEFT JOIN in SQL.",
        "answer": (
            "An INNER JOIN returns only rows where there's a match in both tables — if a row "
            "in the left table has no corresponding row in the right table, it's excluded entirely. "
            "A LEFT JOIN returns all rows from the left table regardless of whether there's a match, "
            "filling in NULLs for the right table's columns when there isn't one. I'd use INNER JOIN "
            "when I only care about complete, matched records — like getting orders that definitely "
            "have a valid customer. I'd use LEFT JOIN when I need to see all records from the primary "
            "table even if related data is missing — like listing all customers and their order count, "
            "including customers with zero orders."
        )
    },
    {
        "id": 4,
        "skill_tag": "PostgreSQL & Database Architecture",
        "question": "How would you design a PostgreSQL schema for tracking user transactions?",
        "answer": (
            "I'd have a users table and a transactions table, with transactions referencing "
            "users via a foreign key on user_id. Each transaction row would have an amount, a status "
            "(pending/completed/failed), and a timestamp. I'd wrap balance updates in a database "
            "transaction using BEGIN/COMMIT to ensure atomicity — so if a transfer fails partway through, "
            "nothing gets committed. For concurrency, I'd use SELECT ... FOR UPDATE to lock the relevant "
            "row when updating a balance, preventing race conditions from simultaneous updates. I'd add "
            "an index on user_id and timestamp since those are the most common query patterns."
        )
    }
]

def main():
    print("=" * 90)
    print("  RUBRIC CEILING VERIFICATION: HAND-WRITTEN STRONG ANSWERS")
    print("=" * 90)
    print(f"Primary Eval Model:     {settings.EVAL_MODEL_PROVIDER} ({settings.EVAL_MODEL_NAME})")
    print(f"Fallback Eval Model:    {settings.EVAL_FALLBACK_MODEL_PROVIDER} ({settings.EVAL_FALLBACK_MODEL_NAME})")
    print(f"Groq API Key Configured: {'YES' if settings.GROQ_API_KEY else 'NO'}\n")

    results = []

    for item in TEST_CASES:
        print("-" * 90)
        print(f"[TEST {item['id']}] Skill: {item['skill_tag']}")
        print(f"Question: \"{item['question']}\"")
        print(f"\nCandidate Answer:\n\"{item['answer']}\"")
        sys.stdout.flush()

        eval_res = evaluate_answer(
            question=item["question"],
            skill_tag=item["skill_tag"],
            answer_text=item["answer"]
        )

        score = float(eval_res.get("score", 0.0))
        reasoning = eval_res.get("reasoning", "")
        red_flag = eval_res.get("red_flag", False)
        provider = eval_res.get("eval_provider", "unknown")
        reached_target = "YES (9-10)" if score >= 9.0 else f"NO ({score}/10)"

        print(f"\n-> [EVAL TIER: {provider}] | Score: {score}/10 | Red Flag: {red_flag}")
        print(f"-> Reasoning: {reasoning}")
        print(f"-> Reached 9-10 Range: {reached_target}")
        sys.stdout.flush()

        results.append({
            "id": item["id"],
            "topic": item["skill_tag"],
            "score": score,
            "reached": score >= 9.0,
            "provider": provider,
            "reasoning": reasoning
        })

    print("\n" + "=" * 90)
    print("  SUMMARY: RUBRIC CEILING RESULTS")
    print("=" * 90)
    print(f"{'#':<3} | {'Topic':<35} | {'Score':<8} | {'Tier':<10} | {'9-10 Reached?'}")
    print("-" * 90)
    for r in results:
        reached_str = "✅ YES" if r["reached"] else "❌ NO"
        print(f"{r['id']:<3} | {r['topic']:<35} | {r['score']:<8.1f} | {r['provider']:<10} | {reached_str}")

    print("=" * 90)

if __name__ == "__main__":
    main()
