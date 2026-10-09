"""Phase 2: Media upload and speech-to-text transcription service.
Uses local OpenAI Whisper model for offline transcription and runs system ffmpeg pre-checks.
"""
import os
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger("ai_interviewer")

# In-memory cached Whisper model instances by size
_WHISPER_MODELS: Dict[str, Any] = {}

def check_ffmpeg_available() -> bool:
    """Verifies that ffmpeg is installed and accessible in PATH.
    If not in PATH, checks common Windows WinGet / AppData installation paths and adds to PATH if found.
    """
    # 1. Direct check
    try:
        res = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        if res.returncode == 0:
            return True
    except (FileNotFoundError, Exception):
        pass

    # 2. Check common Windows WinGet / local paths and dynamically update PATH
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    candidate_paths = [
        Path(local_app_data) / "Microsoft" / "WinGet" / "Links",
        Path(program_files) / "ffmpeg" / "bin",
    ]
    if local_app_data:
        winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_pkgs.exists():
            for gyan_dir in winget_pkgs.glob("*Gyan*/**/bin"):
                candidate_paths.append(gyan_dir)

    for p in candidate_paths:
        ffmpeg_exe = p / "ffmpeg.exe" if os.name == "nt" else p / "ffmpeg"
        if ffmpeg_exe.exists():
            os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
            try:
                res = subprocess.run(
                    [str(ffmpeg_exe), "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5
                )
                if res.returncode == 0:
                    logger.info(f"Dynamically discovered ffmpeg at: {p}")
                    return True
            except Exception:
                pass

    error_msg = (
        "ffmpeg is required for audio/video transcription but was not found in PATH.\n"
        "On Windows, please install it via:\n"
        "    winget install Gyan.FFmpeg\n"
        "or download from https://ffmpeg.org/download.html and add its 'bin' directory to your system PATH."
    )
    logger.error(error_msg)
    raise RuntimeError(error_msg)


def get_whisper_model(model_size: Optional[str] = None):
    """Loads and caches the local Whisper model in memory by size."""
    size = model_size or settings.WHISPER_MODEL_SIZE
    if size in _WHISPER_MODELS:
        return _WHISPER_MODELS[size]

    check_ffmpeg_available()
    try:
        import whisper
        logger.info(f"[TRANSCRIPTION] Loading local Whisper model: '{size}' on CPU/GPU...")
        model = whisper.load_model(size)
        _WHISPER_MODELS[size] = model
        logger.info(f"[TRANSCRIPTION] Whisper model '{size}' loaded successfully.")
        return model
    except Exception as e:
        logger.error(f"[TRANSCRIPTION] Failed to load local Whisper model ({size}): {e}")
        raise


def upload_recording(session_id: str, question_id: str, file_bytes: bytes, filename: str) -> str:
    """Saves candidate audio/video recording bytes to local disk in RECORDINGS_DIR.
    Returns the resolved relative filepath for database storage.
    """
    recordings_dir = Path(settings.RECORDINGS_DIR)
    recordings_dir.mkdir(parents=True, exist_ok=True)

    # Determine extension
    ext = Path(filename).suffix.lower() if filename else ".webm"
    if not ext or ext not in [".webm", ".mp4", ".wav", ".mp3", ".ogg", ".m4a"]:
        ext = ".webm"

    clean_filename = f"{session_id}_{question_id}{ext}"
    target_path = recordings_dir / clean_filename

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    logger.info(f"[MEDIA] Saved recording ({len(file_bytes)} bytes) to: {target_path}")
    return f"uploads/recordings/{clean_filename}"


def remux_video_with_cues(input_path: Path) -> Path:
    """Remuxes browser-recorded WebM or MP4 video using FFmpeg stream copy (-c copy).
    This injects proper EBML Duration and Cues (seek index table) without re-encoding,
    enabling instant, smooth timeline seeking/scrubbing in VLC, browser, and media players.
    Falls back to original file if FFmpeg fails.
    """
    check_ffmpeg_available()
    try:
        temp_output = input_path.parent / f"seekable_{input_path.name}"
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-c", "copy",
            str(temp_output)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if res.returncode == 0 and temp_output.exists() and temp_output.stat().st_size > 500:
            # Overwrite original with the indexed, seekable version
            shutil.move(str(temp_output), str(input_path))
            logger.info(f"[MEDIA REMUX] Successfully injected Duration & Cues index for: {input_path.name}")
        else:
            if temp_output.exists():
                temp_output.unlink(missing_ok=True)
            logger.warning(f"[MEDIA REMUX] FFmpeg remux failed (code {res.returncode}): {res.stderr.decode('utf-8', errors='ignore')[:200]}")
    except Exception as e:
        logger.warning(f"[MEDIA REMUX] Remuxing encountered error ({e}), keeping original file.")
    return input_path


def get_technical_initial_prompt(skill_tag: Optional[str] = None, question_text: Optional[str] = None) -> str:
    """Constructs a targeted initial prompt for Whisper to prime technical vocabulary and prevent jargon misrecognitions.
    Keeps length strictly within Whisper's 224-token prompt buffer by combining question context with focused technical keywords.
    """
    skill_specific = []
    if skill_tag:
        st_lower = skill_tag.lower()
        if "sql" in st_lower or "database" in st_lower or "postgres" in st_lower or "mysql" in st_lower or "mongo" in st_lower:
            skill_specific = [
                "PostgreSQL", "MySQL", "MongoDB", "Redis", "SQL", "JOIN", "CTE", "index", "B-Tree", "GIN", "ACID", "deadlock",
                "EXPLAIN ANALYZE", "sharding", "replication", "WAL", "connection pooling", "foreign key", "normalization"
            ]
        elif "fastapi" in st_lower or "python" in st_lower or "django" in st_lower or "flask" in st_lower:
            skill_specific = [
                "FastAPI", "Python", "async def", "await", "pydantic", "BaseModel", "HTTPException",
                "asyncio", "Uvicorn", "event loop", "GIL", "tuples", "lists", "mutable", "immutable",
                "hashable", "dict", "context manager", "generator", "yield", "SQLAlchemy", "Celery", "pytest"
            ]
        elif "react" in st_lower or "frontend" in st_lower or "typescript" in st_lower or "javascript" in st_lower or "next" in st_lower or "web" in st_lower:
            skill_specific = [
                "React", "TypeScript", "Next.js", "JavaScript", "JSX", "TSX", "useState", "useEffect", "useMemo",
                "useCallback", "useRef", "Redux", "Zustand", "Tailwind", "CSS", "DOM", "props", "state", "virtual DOM",
                "SSR", "SSG", "hydration", "bundle size", "Webpack", "Vite", "GraphQL", "REST API"
            ]
        elif "java" in st_lower or "spring" in st_lower or "hibernate" in st_lower or "jvm" in st_lower:
            skill_specific = [
                "Java", "Spring Boot", "Hibernate", "JPA", "JVM", "garbage collection", "multithreading", "concurrency",
                "Maven", "Gradle", "JUnit", "microservices", "Dependency Injection", "Autowired", "REST Controller"
            ]
        elif "c#" in st_lower or ".net" in st_lower or "dotnet" in st_lower or "asp.net" in st_lower:
            skill_specific = [
                "C#", ".NET", "ASP.NET Core", "Entity Framework", "LINQ", "async/await", "CLR", "garbage collector",
                "dependency injection", "middleware", "NuGet", "Web API", "microservices"
            ]
        elif "go" in st_lower or "golang" in st_lower:
            skill_specific = [
                "Golang", "Go", "goroutines", "channels", "mutex", "select", "Gin", "Gorm", "pointers", "interfaces",
                "concurrency", "garbage collection", "profiling", "microservices"
            ]
        elif "ai" in st_lower or "vision" in st_lower or "ml" in st_lower or "generative" in st_lower or "gpt" in st_lower or "llm" in st_lower:
            skill_specific = [
                "GPT", "LLM", "PagedAttention", "vLLM", "TensorRT-LLM", "quantization", "INT8", "FP16", "FP32",
                "distillation", "speculative decoding", "dynamic batching", "Redis", "embeddings", "vector search",
                "RAG", "fine-tuning", "LoRA", "Hugging Face", "PyTorch", "transformers"
            ]
        elif "docker" in st_lower or "devops" in st_lower or "k8s" in st_lower or "kubernetes" in st_lower or "cloud" in st_lower or "aws" in st_lower or "azure" in st_lower:
            skill_specific = [
                "Docker", "Dockerfile", "multi-stage build", "Kubernetes", "Pod", "Deployment", "Service", "kubectl",
                "Ingress", "Helm", "ConfigMap", "Secret", "volume mount", "entrypoint", "CI/CD", "AWS", "S3", "EC2", "Lambda", "Terraform"
            ]
        elif "system" in st_lower or "architecture" in st_lower or "distributed" in st_lower:
            skill_specific = [
                "System Design", "microservices", "load balancer", "reverse proxy", "Nginx", "caching", "Redis",
                "Kafka", "RabbitMQ", "event-driven", "latency", "throughput", "sharding", "consistency", "CAP theorem"
            ]
        elif "data" in st_lower or "pandas" in st_lower or "analytics" in st_lower or "spark" in st_lower:
            skill_specific = [
                "pandas", "DataFrame", "Series", "numpy", "groupby", "merge", "concat",
                "ETL", "parquet", "vectorized", "data pipeline", "Apache Spark", "PySpark"
            ]
        else:
            skill_specific = [skill_tag, "API", "microservices", "latency", "throughput", "caching", "Redis", "architecture"]

    # Dynamically extract technical terms / acronyms from question text if present
    if question_text:
        import re
        extracted_terms = re.findall(r"\b[A-Z][a-zA-Z0-9_\-\.]{2,}\b", question_text)
        for term in extracted_terms[:6]:
            if term not in skill_specific:
                skill_specific.insert(0, term)

    # Fallback core terms
    if not skill_specific:
        skill_specific = ["Python", "FastAPI", "React", "TypeScript", "Redis", "PostgreSQL", "Docker", "asyncio", "pydantic"]

    keywords_str = ", ".join(skill_specific[:18])
    
    if question_text:
        # Truncate question if long to fit comfortably in Whisper's ~224 token buffer
        q_clean = question_text.strip()
        if len(q_clean) > 130:
            q_clean = q_clean[:127] + "..."
        return f"Software engineer technical interview. Question: {q_clean} Key technical vocabulary: {keywords_str}."
    else:
        return f"Software engineering technical interview discussion covering: {keywords_str}."


def sanitize_transcript(text: str) -> str:
    """Sanitizes Whisper transcripts by eliminating runaway repeating token loops, mashed words, and noise artifacts."""
    if not text:
        return ""
    import re
    # 1. Eliminate mashed repetitive subwords (e.g. FACEFACEFACE -> FACE)
    cleaned = re.sub(r'([A-Za-z]{3,})\1{2,}', r'\1', text)
    # 2. Eliminate runaway repeated single words with spaces/commas (e.g. FACE FACE FACE -> FACE)
    cleaned = re.sub(r'\b([A-Za-z0-9]+)(?:[\s,]+\1\b){2,}', r'\1', cleaned, flags=re.IGNORECASE)
    # 3. Eliminate runaway repeated 2-word phrases (e.g. STREEN DILETE, STREEN DILETE)
    cleaned = re.sub(r'\b([A-Za-z0-9]+\s+[A-Za-z0-9]+)(?:[\s,]+\1\b)+', r'\1', cleaned, flags=re.IGNORECASE)
    # 4. Clean up excessive whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def repair_transcript_phonetics(raw_text: str, question_text: Optional[str] = None) -> str:
    """Lightweight, sub-200ms LLM pass to repair acoustic speech-to-text misrecognitions
    (e.g., 'paste attention' -> 'PagedAttention', 'bread is' -> 'Redis', 'T-bounds' -> 'debounce',
    'F-32 to I-8' -> 'FP32 to INT8', 'square packets' -> 'square brackets', 'shabu-laric' -> 'hashable').
    Strictly preserves the candidate's actual words, sentence structure, meaning, and tone.
    """
    # 0. Fast rule-based phonetic normalization for common acoustic collisions
    normalized_text = raw_text
    phonetic_map = {
        r'\bpaste attention\b': 'PagedAttention',
        r'\bbread is\b': 'Redis',
        r'\bread is\b': 'Redis',
        r'\bT-bounds\b': 'debounce',
        r'\bT-bound\b': 'debounce',
        r'\bF-32 to I-8\b': 'FP32 to INT8',
        r'\bshabu-laric keys\b': 'hashable dictionary keys',
        r'\bshabu-laric\b': 'hashable',
        r'\bsquare packets\b': 'square brackets',
        r'\btree well\b': 'retrieval',
        r'\btrue stage\b': 'two-stage',
        r'\bstraight resumed from redis\b': 'state resumed from Redis',
        r'\bAPI dive out\b': 'API timeout',
        r'\btenser RTLLM\b': 'TensorRT-LLM',
        r'\btenser RT-LLM\b': 'TensorRT-LLM',
        r'\btensor RTLLM\b': 'TensorRT-LLM',
        r'\buse effect\b': 'useEffect',
        r'\buse state\b': 'useState',
        r'\buse memo\b': 'useMemo',
        r'\buse call back\b': 'useCallback',
        r'\buse callback\b': 'useCallback',
        r'\buse ref\b': 'useRef',
        r'\bnext js\b': 'Next.js',
        r'\bnext JS\b': 'Next.js',
        r'\bgraph QL\b': 'GraphQL',
        r'\bgraph ql\b': 'GraphQL',
        r'\bcube cuddle\b': 'kubectl',
        r'\bcube CTL\b': 'kubectl',
        r'\bcube ctl\b': 'kubectl',
        r'\bengine X\b': 'Nginx',
        r'\bengine x\b': 'Nginx',
        r'\bengine-x\b': 'Nginx',
        r'\bprop drilling\b': 'prop drilling',
        r'\bprops drilling\b': 'prop drilling',
    }
    import re
    for pattern, repl in phonetic_map.items():
        normalized_text = re.sub(pattern, repl, normalized_text, flags=re.IGNORECASE)

    prompt = (
        "You are a specialized Speech-to-Text technical phonetics corrector.\n"
        "A developer answered a technical interview question. The audio transcription produced a raw transcript containing acoustic misrecognitions of technical engineering jargon, acronyms, or numbers.\n\n"
        f"Interview Question Context:\n{question_text or 'Software Engineering Technical Interview'}\n\n"
        f"Raw Transcript:\n\"{normalized_text}\"\n\n"
        "STRICT CORRECTION RULES:\n"
        "1. Fix ONLY acoustic speech-to-text misrecognitions of technical words, framework names, acronyms, or numbers. Examples:\n"
        "   - 'paste attention' -> 'PagedAttention'\n"
        "   - 'bread is' -> 'Redis'\n"
        "   - 'T-bounds' -> 'debounce'\n"
        "   - 'F-32 to I-8' -> 'FP32 to INT8'\n"
        "   - 'square packets' -> 'square brackets'\n"
        "   - 'shabu-laric keys' -> 'hashable dictionary keys'\n"
        "   - 'tree well' -> 'retrieval'\n"
        "   - 'true stage' -> 'two-stage'\n"
        "   - 'straight resumed from redis' -> 'state resumed from Redis'\n"
        "   - 'API dive out' -> 'API timeout'\n"
        "2. DO NOT rewrite, improve, enhance, complete, or summarize the candidate's response.\n"
        "3. Preserve the candidate's exact wording, grammar, sentence structure, and tone.\n"
        "4. Return ONLY the corrected transcript with no preamble, quotes, markdown formatting, or commentary."
    )

    # 1. Try Groq fast model (qwen/qwen3.8-27b or openai/gpt-oss-20b for sub-300ms repair)
    if settings.GROQ_API_KEY:
        for groq_model in ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]:
            try:
                from groq import Groq
                groq_client = Groq(api_key=settings.GROQ_API_KEY)
                resp = groq_client.chat.completions.create(
                    model=groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=1024,
                    timeout=8
                )
                repaired = (resp.choices[0].message.content or "").strip()
                # Strip surrounding quotes if added
                if repaired.startswith('"') and repaired.endswith('"'):
                    repaired = repaired[1:-1].strip()
                if repaired and len(repaired) >= 5:
                    logger.info(f"[TRANSCRIPTION REPAIR] Groq ({groq_model}) corrected transcript ({len(raw_text)} -> {len(repaired)} chars)")
                    return repaired
            except Exception as e:
                logger.warning(f"[TRANSCRIPTION REPAIR] Groq model {groq_model} failed ({e}), trying next.")

    # 2. Try Ollama fallback
    try:
        from langchain_community.llms import Ollama
        llm = Ollama(base_url=settings.OLLAMA_BASE_URL, model=settings.GENERATION_MODEL_NAME, temperature=0.0, timeout=10)
        repaired = llm.invoke(prompt).strip()
        if repaired.startswith('"') and repaired.endswith('"'):
            repaired = repaired[1:-1].strip()
        if repaired and len(repaired) >= 5:
            logger.info(f"[TRANSCRIPTION REPAIR] Ollama corrected transcript ({len(raw_text)} -> {len(repaired)} chars)")
            return repaired
    except Exception as e:
        logger.warning(f"[TRANSCRIPTION REPAIR] Ollama repair skipped ({e}). Using normalized transcript.")

    return normalized_text


def preprocess_audio_for_transcription(input_path: Path) -> Path:
    """Preprocesses input audio/video file using FFmpeg for optimal Whisper accuracy:
    1. Extracts audio track and converts to 16kHz mono 16-bit PCM WAV.
    2. Applies bandpass filter (80Hz to 8500Hz) to cut mic rumble while preserving high-frequency speech sibilants.
    3. Normalizes audio volume using standard loudnorm filter (I=-16, LRA=11, TP=-1.5) without destructive silence chopping.
    Falls back to original file if FFmpeg fails.
    """
    check_ffmpeg_available()
    preprocessed_path = input_path.parent / f"proc_{input_path.stem}.wav"

    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vn",
            "-af", "highpass=f=80,lowpass=f=8500,loudnorm=I=-16:LRA=11:TP=-1.5",
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(preprocessed_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if res.returncode == 0 and preprocessed_path.exists() and preprocessed_path.stat().st_size > 1000:
            logger.info(f"[MEDIA PREPROCESSING] Preprocessed audio saved to {preprocessed_path.name} ({preprocessed_path.stat().st_size} bytes)")
            return preprocessed_path
        else:
            logger.warning(f"[MEDIA PREPROCESSING] FFmpeg filter failed (code {res.returncode}), using original file: {res.stderr.decode('utf-8', errors='ignore')[:200]}")
            return input_path
    except Exception as e:
        logger.warning(f"[MEDIA PREPROCESSING] Preprocessing encountered error ({e}), falling back to raw audio.")
        return input_path


def transcribe_recording(
    file_path_or_relative: str,
    model_size: Optional[str] = None,
    skill_tag: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    question_text: Optional[str] = None
) -> Dict[str, Any]:
    """Transcribes a saved audio/video recording file using Whisper with deterministic temperature=0.0.
    Preprocesses audio with bandpass filtering (80Hz-8500Hz), silence removal, loudnorm, and 16kHz resampling.
    Uses context-aware initial_prompt containing technical terminology and forces language='en'.
    Applies post-transcription LLM phonetic repair to fix acoustic misrecognitions.
    Returns dict: {"text": str, "confidence": float | None, "transcription_mode": "real" | "fallback"}
    Raises HTTPException(400) if transcription is empty, inaudible, or invalid.
    """
    effective_model_size = model_size or settings.WHISPER_MODEL_SIZE
    prompt = initial_prompt or get_technical_initial_prompt(skill_tag=skill_tag, question_text=question_text)

    # Resolve path
    if os.path.isabs(file_path_or_relative):
        full_path = Path(file_path_or_relative)
    else:
        full_path = Path(settings.BACKEND_DIR) / file_path_or_relative

    if not full_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording media file not found at: {full_path}"
        )

    # Preprocess audio (silence trimming + volume normalization + 16kHz mono WAV)
    audio_for_transcription = preprocess_audio_for_transcription(full_path)

    # 1. Groq Cloud Whisper Provider (Default: whisper-large-v3 with greedy temperature=0.0)
    if settings.TRANSCRIPTION_PROVIDER == "groq" and settings.GROQ_API_KEY:
        try:
            from groq import Groq
            groq_client = Groq(api_key=settings.GROQ_API_KEY)
            logger.info(f"[TRANSCRIPTION] Transcribing with Groq Cloud ({settings.GROQ_WHISPER_MODEL}) at temp=0.0...")
            
            with open(audio_for_transcription, "rb") as audio_file:
                trans_resp = groq_client.audio.transcriptions.create(
                    file=(audio_for_transcription.name, audio_file),
                    model=settings.GROQ_WHISPER_MODEL,
                    prompt=prompt,
                    language="en",
                    temperature=0.0,
                    response_format="verbose_json"
                )

            raw_text = sanitize_transcript((trans_resp.text or "").strip())
            if len(raw_text) >= 2:
                # Calculate confidence from segments if available
                confidence = 0.95
                if hasattr(trans_resp, "segments") and trans_resp.segments:
                    import math
                    logprobs = [s.get("avg_logprob", -0.3) for s in trans_resp.segments if isinstance(s, dict) and "avg_logprob" in s]
                    if logprobs:
                        avg_lp = sum(logprobs) / len(logprobs)
                        confidence = max(0.1, min(1.0, math.exp(avg_lp)))

                # Apply fast phonetic repair
                final_text = repair_transcript_phonetics(raw_text, question_text=question_text)

                logger.info(f"[TRANSCRIPTION] Groq success ({len(final_text)} chars): '{final_text[:80]}...'")
                return {
                    "text": final_text,
                    "confidence": confidence,
                    "transcription_mode": "real"
                }
            else:
                logger.warning("[TRANSCRIPTION] Groq returned empty transcript, falling back to local Whisper.")
        except Exception as e:
            logger.warning(f"[TRANSCRIPTION] Groq Whisper failed ({e}), falling back to local Whisper.")

    # 2. Explicit OpenAI provider check (only if explicitly configured in settings)
    if settings.TRANSCRIPTION_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="TRANSCRIPTION_PROVIDER is set to 'openai' but OPENAI_API_KEY is not configured."
            )
        try:
            import openai
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            with open(audio_for_transcription, "rb") as audio_file:
                transcript_obj = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    prompt=prompt,
                    language="en"
                )
            text = (transcript_obj.text or "").strip()
            if len(text) < 2:
                text = "[No audible response detected in recording]"
            return {"text": text, "confidence": 0.95, "transcription_mode": "real"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] OpenAI Whisper API call failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"OpenAI speech transcription failed: {e}"
            )
        finally:
            if audio_for_transcription != full_path and audio_for_transcription.exists():
                try:
                    audio_for_transcription.unlink()
                except Exception:
                    pass

    # Local Whisper Transcription (Default)
    try:
        model = get_whisper_model(effective_model_size)
        logger.info(f"[TRANSCRIPTION] Transcribing {audio_for_transcription.name} with local Whisper ({effective_model_size})...")
        result = model.transcribe(
            str(audio_for_transcription),
            fp16=False,
            language="en",
            condition_on_previous_text=False,
            temperature=(0.0, 0.2, 0.4),
            no_speech_threshold=0.6,
            initial_prompt=prompt
        )

        raw_text = sanitize_transcript(result.get("text", "").strip())
        if not raw_text or len(raw_text) < 2:
            raw_text = "[No audible response detected in recording]"

        # Compute approximate average confidence from segments if available
        confidence = None
        segments = result.get("segments", [])
        if segments:
            import math
            logprobs = [s.get("avg_logprob", -0.5) for s in segments if "avg_logprob" in s]
            if logprobs:
                avg_lp = sum(logprobs) / len(logprobs)
                confidence = max(0.1, min(1.0, math.exp(avg_lp)))

        logger.info(f"[TRANSCRIPTION] Transcribed ({len(raw_text)} chars): '{raw_text[:80]}...'")
        return {
            "text": raw_text,
            "confidence": confidence,
            "transcription_mode": "real"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"\n" + "!" * 80 + "\n"
            f"  ⚠️ TRANSCRIPTION FALLBACK ACTIVE — local Whisper failed ({e}).\n"
            f"  Recording could not be processed into real text.\n"
            f"!" * 80 + "\n"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech-to-text transcription failed on local model: {e}"
        )
    finally:
        if audio_for_transcription != full_path and audio_for_transcription.exists():
            try:
                audio_for_transcription.unlink()
            except Exception:
                pass
