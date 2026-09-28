"""Phase 4: Text-To-Speech (TTS) module using Piper TTS for fast, local, zero-cost question delivery.
Downloads and caches natural English Piper ONNX voice models locally and synthesizes WAV audio.
"""
import io
import wave
import urllib.request
import threading
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from app.core.config import settings

logger = logging.getLogger("ai_interviewer")

# In-memory cached PiperVoice instances by voice name
_PIPER_VOICES: Dict[str, Any] = {}
_VOICE_LOCK = threading.Lock()

# Mapping of supported voices to their Hugging Face download URLs
VOICE_URLS = {
    "en_US-lessac-medium": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    },
    "en_US-amy-medium": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
    },
    "en_US-ryan-medium": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json",
    }
}


def ensure_voice_model_downloaded(voice_name: str) -> tuple[Path, Path]:
    """Ensures that the ONNX model and config for the given voice exist locally.
    Downloads them once if not already present.
    """
    piper_models_dir = Path(settings.MODELS_DIR) / "piper"
    piper_models_dir.mkdir(parents=True, exist_ok=True)

    onnx_path = piper_models_dir / f"{voice_name}.onnx"
    json_path = piper_models_dir / f"{voice_name}.onnx.json"

    if not onnx_path.exists() or not json_path.exists():
        urls = VOICE_URLS.get(voice_name, VOICE_URLS["en_US-lessac-medium"])
        logger.info(f"[TTS] Downloading Piper voice model '{voice_name}' from Hugging Face...")
        
        if not onnx_path.exists():
            urllib.request.urlretrieve(urls["onnx"], onnx_path)
            logger.info(f"[TTS] Saved {onnx_path.name} ({onnx_path.stat().st_size} bytes)")
            
        if not json_path.exists():
            urllib.request.urlretrieve(urls["json"], json_path)
            logger.info(f"[TTS] Saved {json_path.name}")

    return onnx_path, json_path


def get_piper_voice(voice_name: Optional[str] = None):
    """Loads and caches the PiperVoice instance in memory with thread-safety."""
    effective_name = voice_name or settings.TTS_VOICE_NAME
    with _VOICE_LOCK:
        if effective_name not in _PIPER_VOICES:
            from piper import PiperVoice
            onnx_path, json_path = ensure_voice_model_downloaded(effective_name)
            logger.info(f"[TTS] Loading Piper voice instance: {effective_name}...")
            voice = PiperVoice.load(str(onnx_path), config_path=str(json_path))
            _PIPER_VOICES[effective_name] = voice
            logger.info(f"[TTS] Piper voice '{effective_name}' loaded successfully into memory.")
        return _PIPER_VOICES[effective_name]


import re
import numpy as np


def normalize_technical_text_for_speech(text: str) -> str:
    """Preprocesses technical interview text so Piper pronounces acronyms, symbols,
    and coding jargon clearly without colliding or fumbling words.
    """
    if not text:
        return ""
    
    t = text
    # Expand common technical acronyms for clear phonetic pronunciation
    t = re.sub(r'\bML\b', 'M L', t)
    t = re.sub(r'\bAI\b', 'A I', t)
    t = re.sub(r'\bAPI\b', 'A P I', t)
    t = re.sub(r'\bAPIs\b', 'A P Is', t)
    t = re.sub(r'\bOOP\b', 'O O P', t)
    t = re.sub(r'\bSQL\b', 'S Q L', t)
    t = re.sub(r'\bNoSQL\b', 'No S Q L', t)
    t = re.sub(r'\bJSON\b', 'JAY-son', t)
    t = re.sub(r'\bHTTP\b', 'H T T P', t)
    t = re.sub(r'\bHTTPS\b', 'H T T P S', t)
    t = re.sub(r'\bREST\b', 'REST', t)
    t = re.sub(r'\bRESTful\b', 'REST-ful', t)
    t = re.sub(r'\bI/O\b', 'I O', t)
    t = re.sub(r'\bCPU\b', 'C P U', t)
    t = re.sub(r'\bGPU\b', 'G P U', t)
    t = re.sub(r'\bRAM\b', 'R A M', t)
    t = re.sub(r'\bORM\b', 'O R M', t)
    t = re.sub(r'\bUUID\b', 'U U I D', t)
    t = re.sub(r'\bCI/CD\b', 'C I C D', t)
    t = re.sub(r'\bAWS\b', 'A W S', t)
    t = re.sub(r'\bGCP\b', 'G C P', t)
    t = re.sub(r'\bDB\b', 'database', t)
    t = re.sub(r'\bDBs\b', 'databases', t)

    # Complexity notation
    t = re.sub(r'\bO\(1\)\b', 'O of 1', t)
    t = re.sub(r'\bO\(n\)\b', 'O of n', t)
    t = re.sub(r'\bO\(log\s*n\)\b', 'O of log n', t)
    t = re.sub(r'\bO\(n\^2\)\b', 'O of n squared', t)

    # Common latin/written abbreviations
    t = re.sub(r'\bvs\.?\b', 'versus', t, flags=re.IGNORECASE)
    t = re.sub(r'\be\.g\.?,?\b', 'for example,', t, flags=re.IGNORECASE)
    t = re.sub(r'\bi\.e\.?,?\b', 'that is,', t, flags=re.IGNORECASE)
    t = re.sub(r'\betc\.?\b', 'etcetera', t, flags=re.IGNORECASE)

    # Normalize multiple whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def synthesize_speech(
    text: str,
    voice_name: Optional[str] = None,
    length_scale: Optional[float] = None
) -> bytes:
    """Synthesizes input text into clear, natural, and articulate WAV audio bytes using Piper TTS.
    - Normalizes technical acronyms and vocabulary.
    - Synthesizes sentence-by-sentence with natural 350ms breathing pauses between clauses.
    - Uses calibrated noise scales for crisp phonetic stability (no fumbling or slurring).
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return b""

    voice = get_piper_voice(voice_name)
    scale = length_scale if length_scale is not None else getattr(settings, "TTS_LENGTH_SCALE", 1.28)

    from piper.config import SynthesisConfig
    syn_config = SynthesisConfig(
        length_scale=scale,
        noise_scale=0.333,
        noise_w_scale=0.8,
        normalize_audio=True
    )

    # Split into clean distinct sentences on punctuation boundaries (. ? !)
    sentences = [s.strip() for s in re.split(r'(?<=[.?!])\s+', clean_text) if s.strip()]
    if not sentences:
        sentences = [clean_text]

    audio_chunks = []
    # 350ms natural breathing silence between sentences @ 22050Hz 16-bit mono
    inter_sentence_silence = np.zeros(int(22050 * 0.35), dtype=np.int16).tobytes()

    with _VOICE_LOCK:
        for idx, sentence in enumerate(sentences):
            phonetic_sentence = normalize_technical_text_for_speech(sentence)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav_file:
                voice.synthesize_wav(phonetic_sentence, wav_file, syn_config=syn_config)

            # Read raw PCM samples from the synthesized sentence WAV
            with wave.open(io.BytesIO(buf.getvalue()), "rb") as r:
                pcm_data = r.readframes(r.getnframes())
                if len(pcm_data) > 0:
                    audio_chunks.append(pcm_data)

            if idx < len(sentences) - 1:
                audio_chunks.append(inter_sentence_silence)

    # Mux all chunks into one unified WAV
    output_buffer = io.BytesIO()
    with wave.open(output_buffer, "wb") as out_wav:
        out_wav.setnchannels(1)
        out_wav.setsampwidth(2)
        out_wav.setframerate(22050)
        out_wav.writeframes(b"".join(audio_chunks))

    wav_bytes = output_buffer.getvalue()
    logger.debug(f"[TTS] Synthesized natural speech for {len(sentences)} sentences (scale={scale}) -> {len(wav_bytes)} WAV bytes.")
    return wav_bytes


def synthesize_and_save_question_audio(
    session_id: str,
    question_id: str,
    text: str,
    voice_name: Optional[str] = None,
    length_scale: Optional[float] = None
) -> str:
    """Synthesizes text for a question, saves the WAV file to uploads/tts/{session_id}_{question_id}.wav,
    and returns the relative URL.
    """
    tts_dir = Path(settings.TTS_DIR)
    tts_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{session_id}_{question_id}.wav"
    target_path = tts_dir / filename

    audio_bytes = synthesize_speech(text, voice_name=voice_name, length_scale=length_scale)
    with open(target_path, "wb") as f:
        f.write(audio_bytes)

    relative_url = f"uploads/tts/{filename}"
    logger.info(f"[TTS] Saved pre-synthesized audio for Q:{question_id} to: {target_path} ({len(audio_bytes)} bytes)")
    return relative_url


def get_question_audio_path(session_id: str, question_id: str) -> Optional[Path]:
    """Returns the Path to the synthesized WAV file if it exists."""
    tts_dir = Path(settings.TTS_DIR)
    filename = f"{session_id}_{question_id}.wav"
    target_path = tts_dir / filename
    if target_path.exists() and target_path.stat().st_size > 0:
        return target_path
    return None

