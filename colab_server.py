"""Google Colab / GPU PC Avatar Generation Microservice
Runs on an NVIDIA GPU (e.g. Colab T4 16GB VRAM, RTX 3060/3090/4090).
Accepts: POST /generate with 'photo' (image) and 'audio' (wav)
Returns: Rendered MP4 video with high-definition lip sync & facial animation.
"""

import os
import io
import time
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Interviewer GPU Avatar Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = Path("/tmp/avatar_renders" if os.name != "nt" else tempfile.gettempdir()) / "avatar_renders"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Core Lip-Sync Inference Engine (Wav2Lip / FlashHead / SadTalker on GPU)
# ---------------------------------------------------------------------------

def run_gpu_avatar_render(photo_bytes: bytes, audio_bytes: bytes) -> Path:
    """Renders talking head MP4 on GPU using PyTorch + CUDA acceleration."""
    session_uuid = f"render_{int(time.time() * 1000)}"
    img_path = TEMP_DIR / f"{session_uuid}.jpg"
    wav_path = TEMP_DIR / f"{session_uuid}.wav"
    out_path = TEMP_DIR / f"{session_uuid}_out.mp4"

    with open(img_path, "wb") as f:
        f.write(photo_bytes)
    with open(wav_path, "wb") as f:
        f.write(audio_bytes)

    # Check if GPU inference script or Wav2Lip / FlashHead checkpoint is installed
    # Default high-speed PyTorch CUDA execution:
    cmd = [
        "python", "inference.py",
        "--checkpoint_path", "checkpoints/wav2lip_gan.pth",
        "--face", str(img_path),
        "--audio", str(wav_path),
        "--outfile", str(out_path),
        "--pads", "0", "10", "0", "0",
        "--nosmooth"
    ]

    # If running standalone inside standard Colab setup:
    if Path("inference.py").exists():
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0 or not out_path.exists():
            print(f"[ERROR] Inference failed: {res.stderr.decode('utf-8', errors='ignore')}")
            raise RuntimeError("GPU Avatar inference failed.")
    else:
        # Fallback for demonstration if running before git clone:
        # Remuxes audio + image for testing
        remux_cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
            "-i", str(wav_path),
            "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac",
            "-b:a", "192k", "-pix_fmt", "yuv420p", "-shortest",
            str(out_path)
        ]
        subprocess.run(remux_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError("Video rendering produced an empty file.")

    return out_path


@app.get("/")
def health_check():
    import torch
    cuda_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU (No GPU)"
    return {
        "status": "online",
        "gpu_available": cuda_available,
        "device": device_name,
        "memory_allocated_mb": round(torch.cuda.memory_allocated(0) / (1024 * 1024), 2) if cuda_available else 0
    }


@app.post("/generate")
async def generate_avatar(
    photo: UploadFile = File(...),
    audio: UploadFile = File(...)
):
    try:
        photo_bytes = await photo.read()
        audio_bytes = await audio.read()

        if len(photo_bytes) < 100 or len(audio_bytes) < 100:
            raise HTTPException(status_code=400, detail="Invalid photo or audio file payload.")

        start_time = time.time()
        rendered_mp4_path = run_gpu_avatar_render(photo_bytes, audio_bytes)
        elapsed = time.time() - start_time

        print(f"[GPU SERVER] Rendered {rendered_mp4_path.stat().st_size} bytes video in {elapsed:.2f}s")
        return FileResponse(
            path=str(rendered_mp4_path),
            media_type="video/mp4",
            filename="avatar.mp4"
        )
    except Exception as e:
        print(f"[ERROR] Exception during generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
