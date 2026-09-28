// Phase 1: Typed API client for backend communication.
import {
  SessionCreateResponse,
  SessionListItem,
  NextQuestionResponse,
  AnswerEvaluation,
  FullReportResponse,
  ProctoringEvent,
  ProctoringFrameResponse,
  CompleteSessionResponse,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail = 'API request failed';
    try {
      const errJson = await res.json();
      errorDetail = errJson.detail || JSON.stringify(errJson);
    } catch {
      errorDetail = await res.text();
    }
    throw new Error(errorDetail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  /**
   * Starts a new interview session by uploading candidate details, JD, and resume file.
   */
  async createSession(formData: FormData): Promise<SessionCreateResponse> {
    const res = await fetch(`${API_BASE}/api/sessions`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse<SessionCreateResponse>(res);
  },

  /**
   * Fetches list of all interview sessions for the recruiter dashboard.
   */
  async listSessions(): Promise<SessionListItem[]> {
    const res = await fetch(`${API_BASE}/api/sessions`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<SessionListItem[]>(res);
  },

  /**
   * Fetches next unanswered question adaptively for an interview session.
   */
  async getNextQuestion(sessionId: string, excludeId?: string): Promise<NextQuestionResponse> {
    const url = excludeId
      ? `${API_BASE}/api/sessions/${sessionId}/next-question?exclude_id=${encodeURIComponent(excludeId)}`
      : `${API_BASE}/api/sessions/${sessionId}/next-question`;
    const res = await fetch(url, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<NextQuestionResponse>(res);
  },

  /**
   * Submits candidate's answer for evaluation.
   */
  async submitAnswer(
    sessionId: string,
    questionId: string,
    answerText: string
  ): Promise<AnswerEvaluation> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question_id: questionId,
        answer_text: answerText,
      }),
    });
    return handleResponse<AnswerEvaluation>(res);
  },

  /**
   * Submits candidate's recorded video/audio answer for transcription & AI evaluation.
   */
  async submitAnswerRecording(
    sessionId: string,
    questionId: string,
    recordingBlob: Blob,
    filename: string = 'recording.webm'
  ): Promise<AnswerEvaluation> {
    const formData = new FormData();
    formData.append('question_id', questionId);
    formData.append('recording_file', recordingBlob, filename);

    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/answer-recording`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse<AnswerEvaluation>(res);
  },

  /**
   * Logs browser-native proctoring telemetry event (tab switch, window blur, multi-screen) with optional screenshot proof.
   */
  async logProctoringEvent(
    sessionId: string,
    payload: { event_type: string; question_id?: string | null; details?: string | null; screenshot_base64?: string | null }
  ): Promise<ProctoringEvent> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/proctoring-event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<ProctoringEvent>(res);
  },

  /**
   * Sends periodic camera frame snapshot for CV person/face presence verification.
   */
  async uploadProctoringFrame(
    sessionId: string,
    frameBlob: Blob,
    questionId?: string | null
  ): Promise<ProctoringFrameResponse> {
    const formData = new FormData();
    formData.append('frame_file', frameBlob, 'frame.jpg');
    if (questionId) {
      formData.append('question_id', questionId);
    }

    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/proctoring-frame`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse<ProctoringFrameResponse>(res);
  },

  /**
   * Uploads the full continuous session master video.
   */
  async uploadSessionVideo(
    sessionId: string,
    videoBlob: Blob,
    filename: string = 'full_session.webm'
  ): Promise<{ session_id: string; session_video_url: string }> {
    const formData = new FormData();
    formData.append('video_file', videoBlob, filename);

    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/session-video`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse<{ session_id: string; session_video_url: string }>(res);
  },

  /**
   * Finalizes the session and computes overall scorecard + summary report + integrity metrics.
   */
  async completeSession(sessionId: string): Promise<CompleteSessionResponse> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<CompleteSessionResponse>(res);
  },

  /**
   * Fetches complete scorecard, AI synthesis, and turn transcript for a session.
   */
  async getReport(sessionId: string): Promise<FullReportResponse> {
    const res = await fetch(`${API_BASE}/api/reports/${sessionId}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<FullReportResponse>(res);
  },

  /**
   * Returns the direct URL to the pre-synthesized Piper TTS WAV audio for a question.
   */
  getQuestionAudioUrl(sessionId: string, questionId: string): string {
    return `${API_BASE}/api/sessions/${sessionId}/questions/${questionId}/audio`;
  },

  /**
   * Returns the direct URL to the pre-rendered Wav2Lip MP4 lip-sync video for a question.
   */
  getQuestionAvatarVideoUrl(sessionId: string, questionId: string): string {
    return `${API_BASE}/api/sessions/${sessionId}/questions/${questionId}/avatar-video`;
  },

  /**
   * Returns the direct URL to the uploaded interviewer portrait photo.
   */
  getInterviewerPhotoUrl(sessionId: string): string {
    return `${API_BASE}/api/sessions/${sessionId}/interviewer-photo`;
  },
};

