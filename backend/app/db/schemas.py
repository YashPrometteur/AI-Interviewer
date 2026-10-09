"""Phase 1: Pydantic models for request validation and response serialization."""
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, EmailStr, Field, ConfigDict

# --- Candidate Schemas ---
class CandidateBase(BaseModel):
    name: str = Field(..., min_length=2, description="Full candidate name")
    email: EmailStr = Field(..., description="Valid candidate email address")

class CandidateOut(CandidateBase):
    id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Question Schemas ---
class QuestionOut(BaseModel):
    id: str
    session_id: str
    text: str
    skill_tag: str
    difficulty: str
    order_index: Union[int, float]
    is_followup: Optional[bool] = False
    parent_question_id: Optional[str] = None
    audio_url: Optional[str] = None
    avatar_video_url: Optional[str] = None
    mouth_amplitude_track: Optional[List[float]] = None
    interviewer_photo_url: Optional[str] = None
    mock: Optional[bool] = False
    model_config = ConfigDict(from_attributes=True)

class SessionQuestionItem(BaseModel):
    id: str
    session_id: str
    text: str
    skill_tag: str
    difficulty: str
    order_index: Union[int, float]
    is_followup: Optional[bool] = False
    parent_question_id: Optional[str] = None
    is_answered: bool = False
    score: Optional[float] = None
    answer_text: Optional[str] = None
    audio_url: Optional[str] = None
    avatar_video_url: Optional[str] = None
    mouth_amplitude_track: Optional[List[float]] = None
    interviewer_photo_url: Optional[str] = None
    mock: Optional[bool] = False
    model_config = ConfigDict(from_attributes=True)

class SessionQuestionsListResponse(BaseModel):
    session_id: str
    total_questions: int
    answered_count: int
    questions: List[SessionQuestionItem]
    current_question_id: Optional[str] = None

class NextQuestionResponse(BaseModel):
    question: Optional[QuestionOut] = None
    remaining_count: int
    is_completed: bool
    message: Optional[str] = None
    interview_mode: Optional[str] = "live"
    answer_capture_type: Optional[str] = "text"
    session_deadline: Optional[datetime] = None
    interviewer_photo_url: Optional[str] = None
    mock: Optional[bool] = False

# --- Answer Schemas ---
class AnswerSubmitRequest(BaseModel):
    question_id: str
    answer_text: str = Field(default="", min_length=0, description="Candidate's typed answer")

class AnswerEvaluationOut(BaseModel):
    answer_id: str
    question_id: str
    score: float
    reasoning: str
    red_flag: bool
    needs_followup: Optional[bool] = False
    followup_question: Optional[str] = None
    followup_reason: Optional[str] = None
    eval_provider: Optional[str] = "mock"  # groq, ollama_fallback, mock
    answer_source: Optional[str] = "text"  # text, video, audio
    recording_url: Optional[str] = None
    transcription_confidence: Optional[float] = None
    transcription_mode: Optional[str] = None  # "real", "fallback", None
    mock: Optional[bool] = False

# --- Proctoring Schemas ---
class ProctoringEventCreate(BaseModel):
    event_type: str = Field(..., description="Type of proctoring event: tab_switch, focus_loss, multi_screen_detected, no_face_detected, multiple_faces_detected, cell_phone_detected, no_audio_detected, suspicious_silence, analysis_error")
    question_id: Optional[str] = None
    details: Optional[str] = None
    screenshot_base64: Optional[str] = Field(None, description="Optional base64 JPEG snapshot captured at warning trigger")

class ProctoringEventOut(BaseModel):
    event_type: str
    severity: str
    timestamp: datetime
    formatted_timestamp: Optional[str] = None
    question_id: Optional[str] = None
    details: Optional[str] = None
    screenshot_url: Optional[str] = None

class ProctoringFrameResponse(BaseModel):
    person_count: Optional[int] = None
    face_count: Optional[int] = None
    phone_detected: Optional[bool] = False
    phone_count: Optional[int] = 0
    event_logged: Optional[str] = None
    severity: Optional[str] = None
    screenshot_url: Optional[str] = None
    success: bool
    error: Optional[str] = None

# --- Report & Transcript Schemas ---
class TranscriptItem(BaseModel):
    question_id: str
    question_text: str
    skill_tag: str
    difficulty: str
    is_followup: Optional[bool] = False
    parent_question_id: Optional[str] = None
    audio_url: Optional[str] = None
    avatar_video_url: Optional[str] = None
    mouth_amplitude_track: Optional[List[float]] = None
    answer_text: Optional[str] = None
    score: Optional[float] = None
    reasoning: Optional[str] = None
    red_flag: Optional[bool] = False
    eval_provider: Optional[str] = "mock"
    answer_source: Optional[str] = "text"
    recording_url: Optional[str] = None
    transcription_confidence: Optional[float] = None
    transcription_mode: Optional[str] = None

class ReportOut(BaseModel):
    id: str
    session_id: str
    summary_text: str
    strengths: List[str]
    weaknesses: List[str]
    recommendation: str  # pass, fail, borderline
    eval_provider: Optional[str] = "mock"
    created_at: datetime
    mock: Optional[bool] = False
    model_config = ConfigDict(from_attributes=True)

class FullReportResponse(BaseModel):
    session_id: str
    candidate_name: str
    candidate_email: str
    job_role: Optional[str] = "Position Candidate"
    status: str
    interview_mode: Optional[str] = "live"
    answer_capture_type: Optional[str] = "text"
    session_deadline: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    overall_score: Optional[float]
    integrity_score: Optional[float] = 10.0
    integrity_flags: Optional[List[str]] = []
    proctoring_events: Optional[List[ProctoringEventOut]] = []
    session_video_url: Optional[str] = None
    interviewer_photo_url: Optional[str] = None
    eval_provider: Optional[str] = "mock"
    created_at: datetime
    completed_at: Optional[datetime]
    report: Optional[ReportOut]
    transcript: List[TranscriptItem]
    mock: Optional[bool] = False

# --- Session Schemas ---
class SessionCreateResponse(BaseModel):
    session_id: str
    candidate_id: str
    candidate_name: str
    total_questions: int
    session_url: str
    interview_mode: Optional[str] = "live"
    answer_capture_type: Optional[str] = "text"
    session_deadline: Optional[datetime] = None
    interviewer_photo_url: Optional[str] = None
    position: Optional[str] = "Software Engineer"
    email_sent: Optional[bool] = True
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    mock: Optional[bool] = False

class SessionListItem(BaseModel):
    id: str
    candidate_id: str
    candidate_name: str
    candidate_email: str
    status: str
    interview_mode: Optional[str] = "live"
    answer_capture_type: Optional[str] = "text"
    session_deadline: Optional[datetime] = None
    interviewer_photo_url: Optional[str] = None
    last_active_at: Optional[datetime] = None
    overall_score: Optional[float]
    integrity_score: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime]
    total_questions: int
    answered_questions: int
    model_config = ConfigDict(from_attributes=True)

class CompleteSessionResponse(BaseModel):
    session_id: str
    status: str
    overall_score: float
    integrity_score: Optional[float] = 10.0
    integrity_flags: Optional[List[str]] = []
    eval_provider: Optional[str] = "mock"
    report: ReportOut
    mock: Optional[bool] = False
