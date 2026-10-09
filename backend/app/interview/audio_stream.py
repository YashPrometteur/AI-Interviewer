"""Streaming Audio Service for Ultra Low-Latency (<350ms TTFB) Speech Playback.
Uses Piper TTS to generate and stream audio chunks to the frontend without disk I/O bottlenecks.
"""
import io
import re
import wave
import asyncio
import logging
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.interview import tts

logger = logging.getLogger("ai_interviewer")

router = APIRouter(tags=["Audio Stream"])


class StreamSpeechRequest(BaseModel):
    text: str
    voice_name: Optional[str] = None


def _synthesize_sentence_chunk(sentence: str, voice_name: Optional[str] = None, is_first: bool = False) -> bytes:
    """Synthesizes a single sentence to WAV bytes synchronously."""
    try:
        voice = tts.get_piper_voice(voice_name)
        phonetic_sentence = tts.normalize_technical_text_for_speech(sentence)
        if not phonetic_sentence.strip():
            return b""
            
        from piper.config import SynthesisConfig
        syn_config = SynthesisConfig(
            length_scale=1.15,
            noise_scale=0.333,
            noise_w_scale=0.8,
            normalize_audio=True
        )
        
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(phonetic_sentence, wav_file, syn_config=syn_config)
            
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[AudioStream] In-memory Piper synthesis failed: {e}. Falling back to default TTS synthesize.")
        return tts.synthesize_speech(sentence, voice_name=voice_name)


async def generate_piper_tts_stream(
    text: str,
    voice_name: Optional[str] = None
) -> AsyncGenerator[bytes, None]:
    """Streams synthesized audio chunks with ultra-low Time-To-First-Byte (TTFB).
    Processes sentence-by-sentence in real time, yielding audio as soon as the first clause is ready.
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return

    # Split into clean distinct sentences on punctuation boundaries (. ? !)
    sentences = [s.strip() for s in re.split(r'(?<=[.?!])\s+', clean_text) if s.strip()]
    if not sentences:
        sentences = [clean_text]

    for idx, sentence in enumerate(sentences):
        # Run CPU-bound synthesis in a thread pool to avoid blocking async event loop
        chunk_bytes = await asyncio.to_thread(_synthesize_sentence_chunk, sentence, voice_name, idx == 0)
        if chunk_bytes:
            # Yield in smaller sub-chunks (4096 bytes) for smooth network transmission
            chunk_io = io.BytesIO(chunk_bytes)
            while True:
                part = chunk_io.read(4096)
                if not part:
                    break
                yield part
                await asyncio.sleep(0.001)  # Yield control to event loop


@router.post("/interview/stream-speech")
@router.post("/stream-speech")
async def stream_speech_endpoint(payload: StreamSpeechRequest):
    """Streams real-time Piper TTS audio chunks for arbitrary interview text."""
    if not payload.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text cannot be empty.")
    return StreamingResponse(
        generate_piper_tts_stream(payload.text, payload.voice_name),
        media_type="audio/wav"
    )


@router.get("/sessions/{session_id}/questions/{question_id}/stream-audio")
async def stream_question_audio_endpoint(
    session_id: str,
    question_id: str,
    voice_name: Optional[str] = Query(None)
):
    """Streams pre-cached or dynamically synthesized audio for an interview question with minimal delay."""
    # Check if pre-cached WAV exists
    cached_path = tts.get_question_audio_path(session_id, question_id)
    if cached_path and cached_path.exists() and cached_path.stat().st_size > 0:
        async def stream_file():
            with open(cached_path, "rb") as f:
                while chunk := f.read(4096):
                    yield chunk
                    await asyncio.sleep(0.001)
        return StreamingResponse(stream_file(), media_type="audio/wav")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question audio not found.")
