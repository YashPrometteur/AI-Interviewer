"""Phase 1: Application configuration & environment variables.
Configured for Ollama-based fast generation (qwen2.5:7b) and Groq evaluation (llama-3.3-70b-versatile)
with automatic fallback to Ollama if Groq is throttled/exhausted.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("ai_interviewer")

# Resolve explicit absolute path to backend/.env and project root .env
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_ENV_PATH = BACKEND_DIR / ".env"
ROOT_ENV_PATH = BACKEND_DIR.parent / ".env"

if BACKEND_ENV_PATH.exists():
    load_dotenv(dotenv_path=BACKEND_ENV_PATH, override=True)
elif ROOT_ENV_PATH.exists():
    load_dotenv(dotenv_path=ROOT_ENV_PATH, override=True)
else:
    load_dotenv(override=True)

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Interviewer"
    MONGODB_URL: str = os.getenv("MONGO_URI", os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "ai_interview")
    
    # Model Providers & Names
    # Generation: Groq (qwen/qwen3.8-27b) with automatic Ollama fallback
    GENERATION_MODEL_PROVIDER: str = "groq"
    GENERATION_MODEL_NAME: str = "qwen/qwen3.8-27b"

    # Evaluation Tier 1 (Primary): Groq
    # Note: Groq periodically deprecates model names. If evaluations fail with model_not_found,
    # check https://console.groq.com/docs/deprecations for the latest supported models.
    EVAL_MODEL_PROVIDER: str = "groq"
    EVAL_MODEL_NAME: str = "openai/gpt-oss-120b"

    # Evaluation Tier 2 (Fallback): Ollama (qwen2.5:7b)
    EVAL_FALLBACK_MODEL_PROVIDER: str = "ollama"
    EVAL_FALLBACK_MODEL_NAME: str = "qwen2.5:7b"

    # API Keys & Local Endpoints
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    
    # Legacy/Optional aliases
    OPENAI_MODEL: str = "gpt-4o"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    
    # Phase 2: Speech-to-Text & Media Configuration
    # TRANSCRIPTION_PROVIDER: "groq" (whisper-large-v3), "local_whisper", or "openai"
    TRANSCRIPTION_PROVIDER: str = "groq"
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"
    # Whisper model size for local fallback inference: "tiny", "base", "small", "medium"
    WHISPER_MODEL_SIZE: str = "medium"
    # Paths
    BACKEND_DIR: str = str(BACKEND_DIR)
    RECORDINGS_DIR: str = os.path.join(str(BACKEND_DIR), "uploads", "recordings")
    TTS_DIR: str = os.path.join(str(BACKEND_DIR), "uploads", "tts")
    AVATAR_VIDEOS_DIR: str = os.path.join(str(BACKEND_DIR), "uploads", "avatar_videos")
    INTERVIEWER_PHOTOS_DIR: str = os.path.join(str(BACKEND_DIR), "uploads", "interviewer_photos")
    MODELS_DIR: str = os.path.join(str(BACKEND_DIR), "models")

    # Phase 4: Text-to-Speech & Follow-Up Configuration
    TTS_VOICE_NAME: str = "en_US-lessac-medium"
    # Controls speech pace: 1.0 is default, > 1.0 (e.g. 1.25 to 1.30) makes speech slower, distinct, and conversational
    TTS_LENGTH_SCALE: float = 1.28
    MAX_FOLLOWUPS_PER_QUESTION: int = 1

    # Phase 5: Avatar Configuration (gpu, local Wav2Lip, or premium D-ID)
    AVATAR_PROVIDER: str = "local"  # "gpu" (Colab / remote GPU microservice), "local" (free Wav2Lip on CPU), or "did" (premium D-ID API)
    AVATAR_GPU_URL: str = ""  # e.g. "https://xxxx-xx.ngrok-free.app/generate" or "http://192.168.1.50:8000/generate"
    D_ID_API_KEY: str = ""
    D_ID_MALE_VOICE: str = "en-US-GuyNeural"
    D_ID_FEMALE_VOICE: str = "en-US-JennyNeural"
    WAV2LIP_CHECKPOINT_URL: str = "https://github.com/justinjohn0306/Wav2Lip/releases/download/models/wav2lip_gan.pth"
    WAV2LIP_MODEL_PATH: str = os.path.join(str(BACKEND_DIR), "models", "wav2lip", "wav2lip_gan.pth")

    # Phase 2: Session Lifecycle & Interview Modes
    ASYNC_SESSION_DEADLINE_DAYS: int = 3
    LIVE_SESSION_TIMEOUT_MINUTES: int = 60

    # Email & SMTP Settings
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "aditi.k@prometteur.in")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Aditi Kumar - Prometteur Solutions")
    SMTP_USE_TLS: bool = True
    FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

    # Auth
    JWT_SECRET: str = "supersecret_ai_interviewer_jwt_key_phase1"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Limits
    MIN_TEXT_LENGTH: int = 50
    MAX_TEXT_LENGTH: int = 15000

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ENV_PATH) if BACKEND_ENV_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

def check_and_log_mock_status():
    """Checks provider keys and logs active routing configuration."""
    info_box = "\n" + "=" * 80 + "\n"
    info_box += "[MODEL & MEDIA ROUTING CONFIGURATION]:\n"
    info_box += f"   - Generation:          {settings.GENERATION_MODEL_PROVIDER} ({settings.GENERATION_MODEL_NAME})\n"
    info_box += f"   - Primary Evaluation:  {settings.EVAL_MODEL_PROVIDER} ({settings.EVAL_MODEL_NAME})\n"
    info_box += f"   - Fallback Evaluation: {settings.EVAL_FALLBACK_MODEL_PROVIDER} ({settings.EVAL_FALLBACK_MODEL_NAME})\n"
    info_box += f"   - Transcription:       {settings.TRANSCRIPTION_PROVIDER} (Whisper: {settings.WHISPER_MODEL_SIZE})\n"
    info_box += f"   - Ollama URL:          {settings.OLLAMA_BASE_URL}\n"
    info_box += f"   - Groq Key:            {'Configured' if settings.GROQ_API_KEY else 'NOT Set (Will trigger Ollama fallback)'}\n"
    info_box += "=" * 80 + "\n"
    try:
        print(info_box)
    except UnicodeEncodeError:
        print(info_box.encode("ascii", errors="replace").decode("ascii"))
    logger.info(info_box)
