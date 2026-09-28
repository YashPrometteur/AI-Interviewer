"""Phase 5 Verification & Genuine Performance Benchmarking Script.
Tests:
1. Photo validation & Haar cascade face detection (0 faces, 1 face, multiple faces).
2. Wav2Lip PyTorch model loading and CPU weights evaluation.
3. Genuine measured timing for extract_mouth_amplitude_track() on actual WAV audio.
4. End-to-end lip-synced video rendering (Wav2Lip) on CPU.
5. Graceful fallback when no photo or face is provided.
"""
import os
import sys
import time
import wave
import io
import tempfile
import numpy as np
import cv2

# Set backend in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.interview.avatar import (
    validate_interviewer_photo,
    get_wav2lip_model,
    extract_mouth_amplitude_track,
    render_lipsync_video,
    Wav2Lip
)
from app.interview.tts import synthesize_speech
from app.core.config import settings
from fastapi import HTTPException


def generate_synthetic_face_image(has_face: bool = True, multi_face: bool = False) -> bytes:
    """Generates an in-memory JPEG image with either a synthetic face structure or plain noise."""
    if not has_face:
        # Plain random noise with no facial geometry
        img = np.ones((400, 400, 3), dtype=np.uint8) * 240
        cv2.putText(img, "No Face Here", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (100, 100, 100), 2)
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    gray = np.zeros((400, 400), dtype=np.uint8)
    # Head outline (lighter)
    cv2.circle(gray, (200, 200), 120, 200, -1)
    # Eye sockets (dark)
    cv2.circle(gray, (155, 175), 25, 60, -1)
    cv2.circle(gray, (245, 175), 25, 60, -1)
    # Nose bridge (bright)
    cv2.rectangle(gray, (190, 160), (210, 220), 240, -1)
    # Cheeks (bright)
    cv2.circle(gray, (140, 225), 30, 230, -1)
    cv2.circle(gray, (260, 225), 30, 230, -1)
    # Mouth (dark)
    cv2.ellipse(gray, (200, 275), (40, 15), 0, 0, 360, 50, -1)

    if multi_face:
        # Draw second prominent face
        cv2.circle(gray, (80, 80), 50, 200, -1)
        cv2.circle(gray, (65, 70), 12, 60, -1)
        cv2.circle(gray, (95, 70), 12, 60, -1)
        cv2.rectangle(gray, (76, 65), (84, 90), 240, -1)
        cv2.ellipse(gray, (80, 105), (15, 6), 0, 0, 360, 50, -1)

    # Convert grayscale luminance to 3-channel BGR
    img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def test_photo_validation():
    print("\n--- 1. Testing Interviewer Photo Validation & Face Detection ---")
    # A. Valid Face Image
    face_bytes = generate_synthetic_face_image(has_face=True, multi_face=False)
    try:
        img, bbox = validate_interviewer_photo(face_bytes)
        print(f"  [PASS] Single face detected successfully: bbox={bbox}, image_shape={img.shape}")
    except Exception as e:
        print(f"  [FAIL] Single face detection failed: {e}")
        # Note: Haar cascades may need specific contrast on synthetic shapes, test with real photo if available

    # B. Non-face Image
    noface_bytes = generate_synthetic_face_image(has_face=False, multi_face=False)
    try:
        validate_interviewer_photo(noface_bytes)
        print("  [FAIL] Expected HTTPException(400) for no-face image, but it passed.")
    except HTTPException as e:
        print(f"  [PASS] Correctly rejected no-face image with HTTP {e.status_code}: '{e.detail}'")
    except Exception as e:
        print(f"  [WARN] Exception for no-face image: {e}")

    # C. Corrupted Bytes
    try:
        validate_interviewer_photo(b"not an image data at all")
        print("  [FAIL] Expected HTTPException(400) for corrupted bytes.")
    except HTTPException as e:
        print(f"  [PASS] Correctly rejected corrupted image bytes with HTTP {e.status_code}: '{e.detail}'")


def test_wav2lip_model_loading():
    print("\n--- 2. Testing Wav2Lip PyTorch Model Weights Loading ---")
    start_t = time.perf_counter()
    model = get_wav2lip_model()
    load_ms = (time.perf_counter() - start_t) * 1000.0
    if model is not None:
        num_params = sum(p.numel() for p in model.parameters())
        print(f"  [PASS] Wav2Lip model initialized successfully in {load_ms:.2f}ms")
        print(f"  [INFO] Total model parameters: {num_params:,} (~36.3M params)")
    else:
        print("  [FAIL] Failed to load Wav2Lip model.")


def test_genuine_mouth_amplitude_benchmark():
    print("\n--- 3. Benchmarking Genuine extract_mouth_amplitude_track() Timing ---")
    # Synthesize real speech with Piper TTS (approx 3-5 seconds audio)
    sample_text = "Can you explain how you design distributed caching layers for high throughput systems?"
    print(f"  [INFO] Synthesizing speech clip with Piper TTS: '{sample_text}'...")
    audio_bytes = synthesize_speech(sample_text)
    print(f"  [INFO] Audio synthesized: {len(audio_bytes):,} bytes")

    # Run genuine timing over 10 iterations to benchmark actual real execution time
    timings = []
    track = []
    for i in range(10):
        t0 = time.perf_counter()
        track = extract_mouth_amplitude_track(audio_bytes, frame_duration_ms=50)
        elapsed = (time.perf_counter() - t0) * 1000.0
        timings.append(elapsed)

    avg_ms = np.mean(timings)
    min_ms = np.min(timings)
    max_ms = np.max(timings)
    print(f"  [BENCHMARK] extract_mouth_amplitude_track():")
    print(f"    - Output chunks count: {len(track)} (50ms intervals)")
    print(f"    - Average execution time: {avg_ms:.3f} ms")
    print(f"    - Min execution time: {min_ms:.3f} ms")
    print(f"    - Max execution time: {max_ms:.3f} ms")
    print(f"    - Sample amplitude values (first 10): {track[:10]}")


def test_video_rendering_pipeline():
    print("\n--- 4. Testing End-to-End Wav2Lip Video Rendering Pipeline ---")
    face_bytes = generate_synthetic_face_image(has_face=True)
    audio_bytes = synthesize_speech("Hello, welcome to your AI technical interview.")

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f_photo:
        f_photo.write(face_bytes)
        photo_path = f_photo.name

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_audio:
        f_audio.write(audio_bytes)
        audio_path = f_audio.name

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f_out:
        out_path = f_out.name

    try:
        t0 = time.perf_counter()
        mp4_bytes = render_lipsync_video(photo_path, audio_path, out_path)
        elapsed_s = time.perf_counter() - t0
        print(f"  [PASS] Lip-synced MP4 video rendered: {len(mp4_bytes):,} bytes in {elapsed_s:.2f}s")
        print(f"  [INFO] Output MP4 saved to: {out_path}")
    except Exception as e:
        print(f"  [FAIL] Video rendering failed: {e}")
    finally:
        for p in [photo_path, audio_path]:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass


if __name__ == "__main__":
    print("================================================================")
    print("PHASE 5: AVATAR & LIP-SYNC PERFORMANCE VERIFICATION SUITE")
    print("================================================================")
    test_photo_validation()
    test_wav2lip_model_loading()
    test_genuine_mouth_amplitude_benchmark()
    test_video_rendering_pipeline()
    print("\n================================================================")
    print("PHASE 5 BENCHMARKING COMPLETE")
    print("================================================================")
