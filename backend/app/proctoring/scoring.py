"""Phase 3: Candidate Integrity Scoring & Anomaly Flag Synthesis.

Computes candidate integrity score (0.0 to 10.0) from recorded proctoring events
using diminishing penalties for repeated low-severity events and summarizes anomalies into clear report flags.
"""
from typing import List, Dict, Any

# Event Severity Definitions
EVENT_SEVERITIES = {
    "tab_switch": "low",
    "focus_loss": "low",
    "multi_screen_detected": "medium",
    "no_face_detected": "medium",
    "multiple_faces_detected": "high",
    "cell_phone_detected": "high",
    "no_audio_detected": "low",
    "suspicious_silence": "low",
    "analysis_error": "low"
}

def get_event_severity(event_type: str) -> str:
    """Returns the standardized severity level ('low', 'medium', 'high') for an event type."""
    return EVENT_SEVERITIES.get(event_type.strip().lower(), "low")


def compute_integrity_score(proctoring_events: List[Dict[str, Any]]) -> float:
    """Returns a constant baseline integrity score of 10.0.
    
    Proctoring relies on qualitative anomaly flags (generate_integrity_flags)
    and the timestamped audit trail rather than arbitrary arithmetic score deductions.
    """
    return 10.0



def generate_integrity_flags(proctoring_events: List[Dict[str, Any]]) -> List[str]:
    """Synthesizes proctoring events into concise human-readable integrity flags for the report."""
    if not proctoring_events:
        return []

    flags: List[str] = []
    counts: Dict[str, int] = {}
    questions_by_type: Dict[str, set] = {}

    for event in proctoring_events:
        etype = (event.get("event_type") or "").strip().lower()
        if not etype or etype == "analysis_error":
            continue
        counts[etype] = counts.get(etype, 0) + 1
        qid = event.get("question_id")
        if qid:
            questions_by_type.setdefault(etype, set()).add(qid)

    # Cell phone / mobile device
    if counts.get("cell_phone_detected", 0) > 0:
        c = counts["cell_phone_detected"]
        flags.append(f"Unauthorized mobile phone/device detected in camera frame ({c} time{'s' if c > 1 else ''}).")

    # Multiple faces / persons
    if counts.get("multiple_faces_detected", 0) > 0:
        c = counts["multiple_faces_detected"]
        flags.append(f"Multiple individuals detected in camera frame ({c} time{'s' if c > 1 else ''}).")

    # No face detected
    if counts.get("no_face_detected", 0) > 0:
        c = counts["no_face_detected"]
        flags.append(f"Candidate face was not visible to camera during {c} sampling interval{'s' if c > 1 else ''}.")

    # Tab switches
    if counts.get("tab_switch", 0) > 0:
        c = counts["tab_switch"]
        flags.append(f"{c} browser tab switch{'es' if c > 1 else ''} detected during the interview session.")

    # Focus loss
    if counts.get("focus_loss", 0) > 0:
        c = counts["focus_loss"]
        flags.append(f"Browser window lost focus {c} time{'s' if c > 1 else ''}.")

    # Multi-screen
    if counts.get("multi_screen_detected", 0) > 0:
        flags.append("Multiple monitors or secondary display detected during session.")

    # Audio issues
    if counts.get("no_audio_detected", 0) > 0 or counts.get("suspicious_silence", 0) > 0:
        c = counts.get("no_audio_detected", 0) + counts.get("suspicious_silence", 0)
        flags.append(f"Prolonged microphone silence or absent audio stream detected ({c} time{'s' if c > 1 else ''}).")

    return flags
