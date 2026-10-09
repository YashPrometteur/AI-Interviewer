"""Phase 5: Avatar & Lip-Sync Video Engine.
Provides neural lip-sync generation for bank questions using Wav2Lip (CPU inference)
and lightweight amplitude-driven mouth animation for live follow-up questions.
"""
import os
import io
import time
import wave
import shutil
import base64
import tempfile
import urllib.request
import threading
import logging
from pathlib import Path
from typing import Optional, Tuple, List

import requests
import cv2
import numpy as np
import librosa
import torch
import torch.nn as nn
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger("ai_interviewer")

_WAV2LIP_MODEL: Optional[nn.Module] = None
_MODEL_LOCK = threading.Lock()


# ============================================================================
# 1. Wav2Lip PyTorch Neural Network Architecture
# ============================================================================

class Conv2d(nn.Module):
    """2D Convolution block with BatchNorm and ReLU, optional residual connection."""
    def __init__(self, cin: int, cout: int, kernel_size: int | Tuple[int, int], stride: int | Tuple[int, int], padding: int, residual: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conv_block = nn.Sequential(
            nn.Conv2d(cin, cout, kernel_size, stride, padding),
            nn.BatchNorm2d(cout)
        )
        self.act = nn.ReLU()
        self.residual = residual

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.conv_block(x)
        if self.residual:
            out = out + x
        return self.act(out)


class Conv2dTranspose(nn.Module):
    """2D Transposed Convolution block with BatchNorm and ReLU."""
    def __init__(self, cin: int, cout: int, kernel_size: int, stride: int, padding: int, output_padding: int = 0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conv_block = nn.Sequential(
            nn.ConvTranspose2d(cin, cout, kernel_size, stride, padding, output_padding=output_padding),
            nn.BatchNorm2d(cout)
        )
        self.act = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.conv_block(x)
        return self.act(out)


class Wav2Lip(nn.Module):
    """Full Wav2Lip generator model mapping 96x96 face + 80x16 mel-spectrogram to lip-synced face."""
    def __init__(self):
        super().__init__()
        self.face_encoder_blocks = nn.ModuleList([
            nn.Sequential(Conv2d(6, 16, kernel_size=7, stride=1, padding=3)),
            nn.Sequential(Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
                          Conv2d(32, 32, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(32, 32, kernel_size=3, stride=1, padding=1, residual=True)),
            nn.Sequential(Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
                          Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True)),
            nn.Sequential(Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
                          Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True)),
            nn.Sequential(Conv2d(128, 256, kernel_size=3, stride=2, padding=1),
                          Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True)),
            nn.Sequential(Conv2d(256, 512, kernel_size=3, stride=2, padding=1),
                          Conv2d(512, 512, kernel_size=3, stride=1, padding=1, residual=True)),
            nn.Sequential(Conv2d(512, 512, kernel_size=3, stride=1, padding=0),
                          Conv2d(512, 512, kernel_size=1, stride=1, padding=0)),
        ])

        self.audio_encoder = nn.Sequential(
            Conv2d(1, 32, kernel_size=3, stride=1, padding=1),
            Conv2d(32, 32, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(32, 32, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(32, 64, kernel_size=3, stride=(3, 1), padding=1),
            Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(64, 128, kernel_size=3, stride=3, padding=1),
            Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(128, 256, kernel_size=3, stride=(3, 2), padding=1),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(256, 512, kernel_size=3, stride=1, padding=0),
            Conv2d(512, 512, kernel_size=1, stride=1, padding=0),
        )

        self.face_decoder_blocks = nn.ModuleList([
            nn.Sequential(Conv2d(512, 512, kernel_size=1, stride=1, padding=0)),
            nn.Sequential(Conv2dTranspose(1024, 512, kernel_size=3, stride=1, padding=0),
                          Conv2d(512, 512, kernel_size=3, stride=1, padding=1, residual=True),),
            nn.Sequential(Conv2dTranspose(1024, 512, kernel_size=3, stride=2, padding=1, output_padding=1),
                          Conv2d(512, 512, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(512, 512, kernel_size=3, stride=1, padding=1, residual=True),),
            nn.Sequential(Conv2dTranspose(768, 384, kernel_size=3, stride=2, padding=1, output_padding=1),
                          Conv2d(384, 384, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(384, 384, kernel_size=3, stride=1, padding=1, residual=True),),
            nn.Sequential(Conv2dTranspose(512, 256, kernel_size=3, stride=2, padding=1, output_padding=1),
                          Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),),
            nn.Sequential(Conv2dTranspose(320, 128, kernel_size=3, stride=2, padding=1, output_padding=1),
                          Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True),),
            nn.Sequential(Conv2dTranspose(160, 64, kernel_size=3, stride=2, padding=1, output_padding=1),
                          Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True),
                          Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True),),
        ])

        self.output_block = nn.Sequential(
            Conv2d(80, 32, kernel_size=3, stride=1, padding=1),
            nn.Conv2d(32, 3, kernel_size=1, stride=1, padding=0),
            nn.Sigmoid()
        )

    def forward(self, audio_sequences: torch.Tensor, face_sequences: torch.Tensor) -> torch.Tensor:
        feats = []
        x = face_sequences
        for f in self.face_encoder_blocks:
            x = f(x)
            feats.append(x)

        audio_feat = self.audio_encoder(audio_sequences)

        x = audio_feat
        for i, f in enumerate(self.face_decoder_blocks):
            if i > 0:
                x = torch.cat((x, feats[-(i)]), dim=1)
            x = f(x)

        x = self.output_block(torch.cat((x, feats[0]), dim=1))
        return x


# ============================================================================
# 2. Model Loading and Face Validation
# ============================================================================

def ensure_wav2lip_model_downloaded() -> Path:
    """Ensures that the Wav2Lip GAN model checkpoint is downloaded and cached locally."""
    target_path = Path(settings.WAV2LIP_MODEL_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if not target_path.exists() or target_path.stat().st_size < 100_000_000:
        logger.info(f"[AVATAR] Downloading Wav2Lip checkpoint to {target_path}...")
        urllib.request.urlretrieve(settings.WAV2LIP_CHECKPOINT_URL, target_path)
        logger.info(f"[AVATAR] Wav2Lip model downloaded ({target_path.stat().st_size} bytes).")

    return target_path


def get_wav2lip_model() -> nn.Module:
    """Loads and caches the Wav2Lip model instance in memory on CPU (thread-safe)."""
    global _WAV2LIP_MODEL
    with _MODEL_LOCK:
        if _WAV2LIP_MODEL is None:
            model_path = ensure_wav2lip_model_downloaded()
            logger.info(f"[AVATAR] Loading Wav2Lip model onto CPU from {model_path}...")
            model = Wav2Lip()
            ckpt = torch.load(str(model_path), map_location="cpu")
            state_dict = ckpt.get("state_dict", ckpt)
            cleaned_state = {k.replace("module.", ""): v for k, v in state_dict.items()}
            model.load_state_dict(cleaned_state, strict=True)
            model.eval()
            _WAV2LIP_MODEL = model
            logger.info("[AVATAR] Wav2Lip model loaded successfully in CPU eval mode.")
        return _WAV2LIP_MODEL


def validate_interviewer_photo(photo_bytes: bytes) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """Validates the uploaded interviewer photo:
    - Verifies valid image data (JPEG, PNG).
    - Detects a frontal face using OpenCV Haar Cascade.
    - If 0 faces found: raises HTTPException(400) asking for a clear front-facing portrait.
    - If >1 face found: raises HTTPException(400) asking for a single-person portrait.
    - Returns (image_bgr, (x, y, w, h)).
    """
    if not photo_bytes or len(photo_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded interviewer photo is empty or too small. Please upload a valid image file."
        )

    nparr = np.frombuffer(photo_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None or img.size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is corrupted or not a valid image format (JPEG/PNG required)."
        )

    # Normalize image dimensions if overly huge (e.g. > 1600px width/height)
    h, w = img.shape[:2]
    if max(h, w) > 1280:
        scale = 1280.0 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60))

    if len(faces) == 0:
        # Retry with more lenient detector settings
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(40, 40))

    if len(faces) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not detect a clear front-facing face in the uploaded interviewer photo. Please upload a clear, front-facing portrait photo."
        )

    if len(faces) > 1:
        # If multiple small false detections, pick the largest face bbox if it's significantly larger
        sorted_faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        primary_area = sorted_faces[0][2] * sorted_faces[0][3]
        second_area = sorted_faces[1][2] * sorted_faces[1][3]
        if second_area > primary_area * 0.4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Multiple faces detected in the interviewer photo. Please upload a portrait photo of a single person."
            )
        face_box = tuple(sorted_faces[0])
    else:
        face_box = tuple(faces[0])

    return img, face_box


def detect_gender_from_photo(img: np.ndarray, face_box: Tuple[int, int, int, int]) -> str:
    """Analyzes the cropped face region to estimate gender (male vs female).
    Uses facial skin tone variance, lower-third luminance/texture (jawline/facial hair),
    and eyebrow-to-eye distance characteristics.
    Returns 'male' or 'female'.
    """
    try:
        fx, fy, fw, fh = face_box
        face_roi = img[max(0, fy):min(img.shape[0], fy + fh), max(0, fx):min(img.shape[1], fx + fw)]
        if face_roi.size == 0:
            return "male"

        h, w = face_roi.shape[:2]
        # Lower third of face (chin / upper lip area)
        lower_face = face_roi[int(h * 0.65):, :]
        gray_lower = cv2.cvtColor(lower_face, cv2.COLOR_BGR2GRAY)
        
        # Upper face (forehead / eyebrows)
        upper_face = face_roi[:int(h * 0.4), :]
        gray_upper = cv2.cvtColor(upper_face, cv2.COLOR_BGR2GRAY)

        # Facial hair / stubble / shadow creates higher texture variance and lower mean luminance on the lower third
        laplacian_lower = cv2.Laplacian(gray_lower, cv2.CV_64F).var()
        mean_lower = np.mean(gray_lower)
        mean_upper = np.mean(gray_upper)

        # Contrast between upper forehead and lower jaw
        contrast_ratio = mean_lower / (mean_upper + 1e-5)

        # If lower face has significant texture or darker stubble shadow -> male
        if laplacian_lower > 180.0 or contrast_ratio < 0.88:
            return "male"
        return "female"
    except Exception as e:
        logger.debug(f"[AVATAR] Gender detection fallback: {e}")
        return "male"


# ============================================================================
# 3. Full Wav2Lip Neural Lip-Sync Rendering (Bank Questions)
# ============================================================================

def _compute_mel_spectrogram(audio_path: str, sr: int = 16000) -> np.ndarray:
    """Computes 80-band log-mel spectrogram matching Wav2Lip's audio feature extractor."""
    wav, _ = librosa.load(audio_path, sr=sr)
    mel = librosa.feature.melspectrogram(
        y=wav,
        sr=sr,
        n_fft=800,
        hop_length=200,
        win_length=800,
        n_mels=80,
        fmin=55,
        fmax=7600
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)
    # Normalize between -4.0 and 4.0
    normalized_mel = np.clip((mel_db + 40.0) / 40.0, 0.0, 1.0) * 8.0 - 4.0
    return normalized_mel


def _get_eye_boxes(img: np.ndarray, face_box: Tuple[int, int, int, int]) -> List[Tuple[int, int, int, int]]:
    """Detects or anatomically locates eye regions in the face image."""
    fx, fy, fw, fh = face_box
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_roi = gray[fy:fy+fh, fx:fx+fw]
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    eyes = eye_cascade.detectMultiScale(face_roi[:int(fh * 0.62), :], 1.08, 3, minSize=(int(fw * 0.12), int(fh * 0.12)))

    valid_eyes = []
    left_eyes = [e for e in eyes if e[0] < fw * 0.45]
    right_eyes = [e for e in eyes if e[0] >= fw * 0.45]

    if len(left_eyes) >= 1 and len(right_eyes) >= 1:
        le = sorted(left_eyes, key=lambda e: e[2] * e[3], reverse=True)[0]
        re = sorted(right_eyes, key=lambda e: e[2] * e[3], reverse=True)[0]
        for ex, ey, ew, eh in [le, re]:
            valid_eyes.append((int(fx + ex), int(fy + ey), int(ew), int(eh)))
    else:
        # Standard human facial proportion landmarks fallback
        valid_eyes = [
            (int(fx + fw * 0.16), int(fy + fh * 0.28), int(fw * 0.30), int(fh * 0.22)),
            (int(fx + fw * 0.54), int(fy + fh * 0.28), int(fw * 0.30), int(fh * 0.22))
        ]
    return valid_eyes


def _apply_eye_blink(
    img: np.ndarray,
    eye_boxes: List[Tuple[int, int, int, int]],
    blink_factor: float
) -> np.ndarray:
    """Applies a smooth, feathered eyelid closure to the eye regions based on blink_factor (0.0=open, 1.0=closed)."""
    if blink_factor <= 0.001:
        return img.copy()

    res = img.copy()
    for (ex, ey, ew, eh) in eye_boxes:
        pad_y = int(eh * 0.2)
        y_top = max(0, ey - pad_y)
        y_bot = min(img.shape[0], ey + eh + pad_y)
        x_left = max(0, ex)
        x_right = min(img.shape[1], ex + ew)

        crop = img[y_top:y_bot, x_left:x_right]
        ch, cw = crop.shape[:2]
        if ch < 8 or cw < 8:
            continue

        # Upper eyelid texture sampling
        upper_lid = crop[0:max(3, int(ch * 0.35)), :]
        stretched = cv2.resize(upper_lid, (cw, ch), interpolation=cv2.INTER_CUBIC)

        # Natural lash crease seam line
        lash_y = int(ch * 0.65)
        thick = max(1, int(ch * 0.06))
        for ly in range(max(0, lash_y - thick), min(ch, lash_y + thick + 1)):
            alpha = 1.0 - abs(ly - lash_y) / (thick + 1)
            stretched[ly, :] = (stretched[ly, :].astype(np.float32) * (1.0 - 0.35 * alpha)).astype(np.uint8)

        # Soft elliptical feather mask
        mask = np.zeros((ch, cw), dtype=np.float32)
        cv2.ellipse(mask, (cw // 2, ch // 2), (int(cw * 0.46), int(ch * 0.42)), 0, 0, 360, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (7, 7), 2)
        mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)

        b = np.clip(blink_factor, 0.0, 1.0)
        warped = (stretched.astype(np.float32) * b + crop.astype(np.float32) * (1.0 - b))
        blended = (warped * mask + crop.astype(np.float32) * (1.0 - mask)).astype(np.uint8)
        res[y_top:y_bot, x_left:x_right] = blended

    return res


def _compute_natural_blink_schedule(total_frames: int, fps: int = 25, seed: int = 42) -> np.ndarray:
    """Computes a spontaneous timeline of natural eye blinks (every ~2.5s-4.2s), completely unlinked to speech."""
    np.random.seed(seed)
    factors = np.zeros(total_frames, dtype=np.float32)
    blink_profile = [0.25, 0.65, 1.0, 0.70, 0.30]  # 5-frame natural blink (~200ms)

    current_frame = int(fps * 1.2)  # First spontaneous blink around 1.2s
    while current_frame + len(blink_profile) < total_frames:
        for idx, val in enumerate(blink_profile):
            if current_frame + idx < total_frames:
                factors[current_frame + idx] = val
        interval = np.random.randint(int(fps * 2.5), int(fps * 4.2))
        current_frame += len(blink_profile) + interval
    return factors


def render_lipsync_video(
    photo_path: str,
    audio_path: str,
    output_path: Optional[str] = None
) -> bytes:
    """Renders a full Wav2Lip neural lip-sync MP4 video from an interviewer photo and TTS audio file,
    incorporating spontaneous natural eye blinking unlinked from speech.
    Runs on CPU with batching. Muxes video + audio via ffmpeg into an H.264 MP4.
    """
    start_time = time.perf_counter()
    img = cv2.imread(photo_path)
    if img is None:
        raise ValueError(f"Could not read interviewer photo at: {photo_path}")

    # Detect face box in the photo - always select the primary largest face
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
    if len(faces) == 0:
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=2, minSize=(40, 40))
        if len(faces) == 0:
            h, w = img.shape[:2]
            face_box = (int(w * 0.25), int(h * 0.2), int(w * 0.5), int(h * 0.5))
        else:
            sorted_faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
            face_box = tuple(sorted_faces[0])
    else:
        sorted_faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        face_box = tuple(sorted_faces[0])

    fx, fy, fw, fh = face_box
    eye_boxes = _get_eye_boxes(img, face_box)

    # Add vertical padding to ensure lower chin is fully captured
    pad_y1 = int(fh * 0.05)
    pad_y2 = int(fh * 0.15)
    pad_x = int(fw * 0.05)

    img_h, img_w = img.shape[:2]
    y1 = max(0, fy - pad_y1)
    y2 = min(img_h, fy + fh + pad_y2)
    x1 = max(0, fx - pad_x)
    x2 = min(img_w, fx + fw + pad_x)

    face_crop = img[y1:y2, x1:x2]
    crop_h, crop_w = face_crop.shape[:2]

    # Convert to RGB for Wav2Lip network input
    face_crop_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
    face_96 = cv2.resize(face_crop_rgb, (96, 96))
    face_96_masked = face_96.copy()
    # Mask the lower half (mouth region) with zeros
    face_96_masked[48:, :] = 0

    # Prepare 6-channel input: (masked_face, reference_face) normalized to [0, 1]
    input_face = np.concatenate([face_96_masked, face_96], axis=2) / 255.0
    input_face_tensor = torch.FloatTensor(input_face).permute(2, 0, 1).unsqueeze(0)  # Shape: (1, 6, 96, 96)

    # Compute audio mel spectrogram
    mel = _compute_mel_spectrogram(audio_path, sr=16000)
    fps = 25
    mel_step_size = 16  # 16 mel frames corresponds to 200ms audio window
    total_video_frames = int(librosa.get_duration(path=audio_path) * fps)
    total_video_frames = max(1, total_video_frames)

    # Compute spontaneous natural eye blink schedule (unlinked from speech)
    blink_schedule = _compute_natural_blink_schedule(
        total_video_frames,
        fps=fps,
        seed=int(hash(photo_path + audio_path) % 100000)
    )

    # Prepare audio chunks for each video frame
    mel_chunks = []
    for i in range(total_video_frames):
        start_idx = int(i * (mel.shape[1] / total_video_frames))
        end_idx = start_idx + mel_step_size
        if end_idx <= mel.shape[1]:
            chunk = mel[:, start_idx:end_idx]
        else:
            chunk = np.zeros((80, mel_step_size), dtype=np.float32)
            avail = mel[:, start_idx:]
            chunk[:, :avail.shape[1]] = avail
        mel_chunks.append(chunk)

    model = get_wav2lip_model()
    batch_size = 16
    generated_mouth_crops = []

    with torch.no_grad():
        for b_start in range(0, len(mel_chunks), batch_size):
            b_chunks = mel_chunks[b_start:b_start + batch_size]
            b_size = len(b_chunks)

            audio_batch = torch.FloatTensor(np.array(b_chunks)).unsqueeze(1)  # (B, 1, 80, 16)
            face_batch = input_face_tensor.repeat(b_size, 1, 1, 1)  # (B, 6, 96, 96)

            preds = model(audio_batch, face_batch)  # (B, 3, 96, 96) in [0, 1]
            preds_np = (preds.permute(0, 2, 3, 1).cpu().numpy() * 255.0).astype(np.uint8)

            for p in preds_np:
                generated_mouth_crops.append(p)

    # Temporary directory for video rendering and audio muxing
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_video_path = os.path.join(tmpdir, "raw_video.avi")
        final_mp4_path = os.path.join(tmpdir, "final.mp4")

        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        out_writer = cv2.VideoWriter(raw_video_path, fourcc, fps, (img_w, img_h))

        # Soft feather mask for seamless face boundary blending
        mask_96 = np.zeros((96, 96, 3), dtype=np.float32)
        mask_96[48:, :] = 1.0
        mask_96 = cv2.GaussianBlur(mask_96, (9, 9), 4)

        for frame_idx in range(total_video_frames):
            blink_val = float(blink_schedule[frame_idx])
            blinked_base = _apply_eye_blink(img, eye_boxes, blink_val) if blink_val > 0.001 else img.copy()

            pred_96 = generated_mouth_crops[min(frame_idx, len(generated_mouth_crops) - 1)]
            # Blend 96x96 predicted mouth onto base face
            blended_96 = (pred_96.astype(np.float32) * mask_96 + face_96.astype(np.float32) * (1.0 - mask_96)).astype(np.uint8)
            # Convert blended face from RGB back to BGR for OpenCV VideoWriter
            blended_96_bgr = cv2.cvtColor(blended_96, cv2.COLOR_RGB2BGR)
            restored_face = cv2.resize(blended_96_bgr, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)

            frame = blinked_base.copy()
            frame[y1:y2, x1:x2] = restored_face
            out_writer.write(frame)

        out_writer.release()

        # Mux audio into video using ffmpeg
        ffmpeg_cmd = (
            f'ffmpeg -y -i "{raw_video_path}" -i "{audio_path}" '
            f'-c:v libx264 -pix_fmt yuv420p -preset fast -c:a aac -b:a 128k -shortest "{final_mp4_path}"'
        )
        os.system(ffmpeg_cmd)

        if not os.path.exists(final_mp4_path) or os.path.getsize(final_mp4_path) == 0:
            # Fallback direct copy if ffmpeg transcode issue
            shutil.copy(raw_video_path, final_mp4_path)

        with open(final_mp4_path, "rb") as f:
            mp4_bytes = f.read()

    elapsed = time.perf_counter() - start_time
    logger.info(f"[AVATAR] Rendered {total_video_frames} lip-sync frames with eye blinking ({total_video_frames/fps:.2f}s video) in {elapsed:.2f}s on CPU.")

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(mp4_bytes)

    return mp4_bytes


def render_gpu_avatar_video(
    photo_path: str,
    audio_path: str,
    output_path: Optional[str] = None
) -> bytes:
    """Renders high-fidelity talking avatar MP4 video using an external GPU microservice (e.g. Google Colab T4 or remote GPU PC).
    Sends photo image and TTS audio via multipart/form-data HTTP POST request and receives the rendered MP4.
    """
    gpu_url = (os.getenv("AVATAR_GPU_URL") or settings.AVATAR_GPU_URL or "").strip()
    if not gpu_url:
        raise ValueError("AVATAR_GPU_URL is not configured in backend/.env")

    # If user provided base URL without /generate, append it
    if not gpu_url.endswith("/generate") and not gpu_url.endswith("/render"):
        gpu_url = gpu_url.rstrip("/") + "/generate"

    logger.info(f"[GPU AVATAR] Sending photo and audio to remote GPU avatar server: {gpu_url}...")
    start_t = time.perf_counter()

    with open(photo_path, "rb") as pf, open(audio_path, "rb") as af:
        files = {
            "photo": ("photo.jpg", pf, "image/jpeg"),
            "audio": ("audio.wav", af, "audio/wav")
        }
        # Allow up to 600s (10 min) for diffusion model inference & cold-start
        res = requests.post(gpu_url, files=files, timeout=600)

    if res.status_code != 200:
        raise RuntimeError(f"GPU Avatar server returned HTTP {res.status_code}: {res.text[:300]}")

    mp4_bytes = res.content
    if len(mp4_bytes) < 1000:
        raise RuntimeError(f"GPU Avatar server returned invalid/empty video ({len(mp4_bytes)} bytes)")

    elapsed = time.perf_counter() - start_t
    logger.info(f"[GPU AVATAR] Successfully received rendered MP4 video ({len(mp4_bytes)} bytes) in {elapsed:.2f}s from GPU server.")

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(mp4_bytes)

    return mp4_bytes


def render_did_video(
    photo_path: str,
    text: str,
    gender: str = "female",
    output_path: Optional[str] = None
) -> bytes:
    """Renders a studio-grade 3D talking avatar MP4 video using the D-ID Talks API.
    Provides natural 3D head motion, realistic eye blinks, torso movement, and Azure neural voice.
    """
    if not settings.D_ID_API_KEY:
        raise ValueError("D_ID_API_KEY is not configured in backend/.env")

    api_key = settings.D_ID_API_KEY.strip()
    auth_header = {"Authorization": f"Basic {api_key}"}

    # 1. Upload photo to D-ID images endpoint (or use cached S3 URL)
    with open(photo_path, "rb") as f:
        img_bytes = f.read()

    logger.info(f"[D-ID] Uploading interviewer photo ({len(img_bytes)} bytes) to D-ID images...")
    upload_res = requests.post(
        "https://api.d-id.com/images",
        headers=auth_header,
        files={"image": ("photo.jpg", img_bytes, "image/jpeg")},
        timeout=25
    )
    if upload_res.status_code not in (200, 201):
        raise RuntimeError(f"D-ID image upload failed with status {upload_res.status_code}: {upload_res.text}")

    image_s3_url = upload_res.json().get("url")
    if not image_s3_url:
        raise RuntimeError(f"D-ID image upload did not return URL: {upload_res.text}")

    voice_id = settings.D_ID_MALE_VOICE if gender == "male" else settings.D_ID_FEMALE_VOICE

    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "source_url": image_s3_url,
        "script": {
            "type": "text",
            "input": text,
            "provider": {
                "type": "microsoft",
                "voice_id": voice_id
            }
        },
        "config": {
            "fluent": True,
            "pad_audio": 0.0,
            "stitch": False,
            "align_driver": True
        }
    }

    logger.info(f"[D-ID] Creating 3D talk animation for text ({len(text)} chars) with voice '{voice_id}'...")
    res = requests.post("https://api.d-id.com/talks", json=payload, headers=headers, timeout=20)
    if res.status_code not in (200, 201):
        raise RuntimeError(f"D-ID talk creation failed with status {res.status_code}: {res.text}")

    talk_id = res.json().get("id")
    if not talk_id:
        raise RuntimeError(f"No talk ID returned from D-ID: {res.text}")

    # Poll for completion (D-ID cloud GPU rendering usually completes in 5-25s)
    poll_url = f"https://api.d-id.com/talks/{talk_id}"
    max_wait = 180
    start_time = time.time()
    result_url = None

    while time.time() - start_time < max_wait:
        poll_res = requests.get(poll_url, headers=headers, timeout=10)
        if poll_res.status_code == 200:
            status_data = poll_res.json()
            talk_status = status_data.get("status")
            if talk_status == "done":
                result_url = status_data.get("result_url")
                break
            elif talk_status == "error":
                raise RuntimeError(f"D-ID rendering error: {status_data}")
        time.sleep(1.0)

    if not result_url:
        raise TimeoutError("D-ID video rendering timed out.")

    # Download rendered MP4 video
    dl_res = requests.get(result_url, timeout=30)
    if dl_res.status_code != 200:
        raise RuntimeError(f"Failed to download rendered D-ID video from {result_url}")

    mp4_bytes = dl_res.content
    logger.info(f"[D-ID] Video successfully rendered ({len(mp4_bytes)} bytes) in {time.time() - start_time:.2f}s.")

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(mp4_bytes)

    return mp4_bytes


# ============================================================================
# 4. Lightweight Real-Time Amplitude Track Extraction (Follow-Ups)
# ============================================================================

def extract_mouth_amplitude_track(
    audio_bytes: bytes,
    frame_duration_ms: int = 50
) -> List[float]:
    """Calculates RMS audio volume amplitude envelope per 50ms chunk for lightweight real-time mouth animation.
    Fast execution on CPU without neural inference.
    Returns normalized float values [0.0 - 1.0].
    """
    start_t = time.perf_counter()
    if not audio_bytes or len(audio_bytes) < 44:
        return []

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            n_channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            framerate = wav.getframerate()
            n_frames = wav.getnframes()
            raw_frames = wav.readframes(n_frames)

        if sample_width == 2:
            audio_samples = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32)
        elif sample_width == 4:
            audio_samples = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32)
        else:
            audio_samples = np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32) - 128.0

        if n_channels > 1:
            audio_samples = audio_samples.reshape(-1, n_channels).mean(axis=1)

        samples_per_chunk = max(1, int(framerate * (frame_duration_ms / 1000.0)))
        num_chunks = int(np.ceil(len(audio_samples) / samples_per_chunk))

        rms_values = []
        for i in range(num_chunks):
            chunk = audio_samples[i * samples_per_chunk:(i + 1) * samples_per_chunk]
            if len(chunk) > 0:
                rms = np.sqrt(np.mean(chunk ** 2))
                rms_values.append(rms)
            else:
                rms_values.append(0.0)

        rms_arr = np.array(rms_values, dtype=np.float32)
        max_val = np.percentile(rms_arr, 95) if len(rms_arr) > 0 else 1.0
        if max_val <= 0:
            max_val = np.max(rms_arr) if np.max(rms_arr) > 0 else 1.0

        normalized = np.clip(rms_arr / max_val, 0.0, 1.0)
        result = [round(float(v), 3) for v in normalized]

        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        logger.debug(f"[AVATAR] Amplitude extraction: {len(result)} chunks in {elapsed_ms:.2f}ms")
        return result

    except Exception as e:
        logger.warning(f"[AVATAR] Amplitude extraction error: {e}")
        return []


# ============================================================================
# 5. Path Resolvers
# ============================================================================

def get_avatar_video_path(session_id: str, question_id: str) -> Optional[Path]:
    """Returns the Path to the pre-rendered MP4 video if it exists."""
    target_dir = Path(settings.AVATAR_VIDEOS_DIR)
    filename = f"{session_id}_{question_id}.mp4"
    target_path = target_dir / filename
    if target_path.exists() and target_path.stat().st_size > 1000:
        return target_path
    return None


def get_interviewer_photo_path(session_id: str) -> Optional[Path]:
    """Returns the Path to the uploaded interviewer portrait photo if it exists."""
    target_dir = Path(settings.INTERVIEWER_PHOTOS_DIR)
    filename = f"{session_id}.jpg"
    target_path = target_dir / filename
    if target_path.exists() and target_path.stat().st_size > 100:
        return target_path
    return None
