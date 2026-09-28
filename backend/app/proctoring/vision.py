"""Phase 3: Computer Vision module for periodic frame-sampling proctoring.

Implements a two-pass detection architecture:
1. YOLOv8 (yolov8n.pt, class=0 'person') -> person_count (detects presence of candidate and any additional persons in frame).
2. OpenCV Haar Cascade (haarcascade_frontalface_default.xml) -> face_count (detects direct frontal face visibility to camera).
"""
import logging
from typing import Dict, Any, Optional
import cv2
import numpy as np

logger = logging.getLogger("ai_interviewer")

_YOLO_MODEL = None
_FACE_CASCADE = None


def get_face_cascade():
    """Loads and caches OpenCV frontal face Haar cascade."""
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _FACE_CASCADE = cv2.CascadeClassifier(cascade_path)
    return _FACE_CASCADE


def get_yolo_model():
    """Loads and caches YOLOv8 nano model for person detection."""
    global _YOLO_MODEL
    if _YOLO_MODEL is None:
        from ultralytics import YOLO
        _YOLO_MODEL = YOLO("yolov8n.pt")
    return _YOLO_MODEL


def analyze_frame(frame_bytes: bytes) -> Dict[str, Any]:
    """Analyzes a single video frame JPEG/PNG byte stream.
    
    Returns:
        {
            "person_count": Optional[int],   # Count of people detected by YOLOv8 (None on analysis failure)
            "face_count": Optional[int],     # Count of frontal faces detected by OpenCV (None on analysis failure)
            "success": bool,
            "error": Optional[str]
        }
    """
    if not frame_bytes or len(frame_bytes) < 100:
        return {"person_count": None, "face_count": None, "success": False, "error": "Empty or truncated frame data"}

    try:
        # Decode byte buffer into OpenCV BGR image
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"person_count": None, "face_count": None, "success": False, "error": "Failed to decode image bytes"}

        # 1. Person & Object Detection Pass via YOLOv8 (COCO class 0 = 'person', class 67 = 'cell phone')
        person_boxes = []
        person_count = 0
        phone_detected = False
        phone_count = 0
        try:
            yolo = get_yolo_model()
            results = yolo(img, verbose=False, conf=0.40)
            if results and len(results) > 0 and results[0].boxes is not None:
                for b in results[0].boxes:
                    cls_id = int(b.cls[0])
                    conf_val = float(b.conf[0])
                    if cls_id == 0 and conf_val >= 0.50:
                        coords = [float(c) for c in b.xyxy[0]]
                        person_boxes.append(coords)
                    elif cls_id == 67 and conf_val >= 0.40:  # COCO 67 = 'cell phone'
                        phone_detected = True
                        phone_count += 1
                person_count = len(person_boxes)
        except Exception as e:
            logger.warning(f"[PROCTORING VISION] YOLOv8 person/object detection pass failed: {e}")

        # 2. Face Detection Pass via OpenCV Haar Cascade (Tuned minNeighbors=8, minSize=(80,80))
        face_count = 0
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            face_cascade = get_face_cascade()
            raw_faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.15,
                minNeighbors=8,
                minSize=(80, 80)
            )

            if len(raw_faces) > 0:
                if person_boxes:
                    # Spatial Cross-Validation: Keep only faces that fall inside a detected person's body box
                    valid_faces = []
                    for (fx, fy, fw, fh) in raw_faces:
                        fc_x = fx + (fw / 2.0)
                        fc_y = fy + (fh / 2.0)
                        # Check if face center falls within any person bounding box
                        inside_person = any(
                            px1 <= fc_x <= px2 and py1 <= fc_y <= py2
                            for (px1, py1, px2, py2) in person_boxes
                        )
                        if inside_person:
                            valid_faces.append((fx, fy, fw, fh))

                    # If only 1 person is detected, cap face count to 1 (prevents duplicate cascade hits on one face)
                    if person_count == 1:
                        face_count = 1 if len(valid_faces) >= 1 else 0
                    else:
                        face_count = len(valid_faces)
                else:
                    # Fallback when webcam is tightly zoomed on face and YOLO body detection is absent
                    face_count = len(raw_faces)
        except Exception as e:
            logger.warning(f"[PROCTORING VISION] Face detection pass failed: {e}")

        return {
            "person_count": person_count,
            "face_count": face_count,
            "phone_detected": phone_detected,
            "phone_count": phone_count,
            "success": True,
            "error": None
        }

    except Exception as e:
        logger.error(f"[PROCTORING VISION] Frame analysis encountered unexpected error: {e}")
        return {
            "person_count": None,
            "face_count": None,
            "success": False,
            "error": str(e)
        }
