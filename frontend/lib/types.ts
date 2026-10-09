export interface Candidate {
  id: string;
  name: string;
  email: string;
  created_at: string;
}

export interface Question {
  id: string;
  session_id: string;
  text: string;
  skill_tag: string;
  difficulty: 'easy' | 'medium' | 'hard';
  order_index: number;
  is_followup?: boolean;
  parent_question_id?: string | null;
  audio_url?: string | null;
  avatar_video_url?: string | null;
  mouth_amplitude_track?: number[] | null;
  interviewer_photo_url?: string | null;
  mock?: boolean;
}

export interface SessionQuestionItem {
  id: string;
  session_id: string;
  text: string;
  skill_tag: string;
  difficulty: 'easy' | 'medium' | 'hard' | string;
  order_index: number;
  is_followup?: boolean;
  parent_question_id?: string | null;
  is_answered: boolean;
  score?: number | null;
  answer_text?: string | null;
  audio_url?: string | null;
  avatar_video_url?: string | null;
  mouth_amplitude_track?: number[] | null;
  interviewer_photo_url?: string | null;
  mock?: boolean;
}

export interface SessionQuestionsListResponse {
  session_id: string;
  total_questions: number;
  answered_count: number;
  questions: SessionQuestionItem[];
}

export interface NextQuestionResponse {
  question: Question | null;
  remaining_count: number;
  is_completed: boolean;
  message?: string;
  interview_mode?: 'live' | 'async';
  answer_capture_type?: 'text' | 'video';
  session_deadline?: string | null;
  interviewer_photo_url?: string | null;
  mock?: boolean;
}

export interface AnswerEvaluation {
  answer_id: string;
  question_id: string;
  score: number;
  reasoning: string;
  red_flag: boolean;
  needs_followup?: boolean;
  followup_question?: string | null;
  followup_reason?: string | null;
  eval_provider?: string;
  answer_source?: 'text' | 'video' | 'audio';
  recording_url?: string | null;
  transcription_confidence?: number | null;
  transcription_mode?: 'real' | 'fallback' | null;
  mock?: boolean;
}

export interface Report {
  id: string;
  session_id: string;
  summary_text: string;
  strengths: string[];
  weaknesses: string[];
  recommendation: 'pass' | 'fail' | 'borderline';
  created_at: string;
  eval_provider?: string;
  mock?: boolean;
}

export interface TranscriptItem {
  question_id: string;
  question_text: string;
  skill_tag: string;
  difficulty: string;
  is_followup?: boolean;
  parent_question_id?: string | null;
  audio_url?: string | null;
  avatar_video_url?: string | null;
  mouth_amplitude_track?: number[] | null;
  answer_text?: string | null;
  score?: number | null;
  reasoning?: string | null;
  red_flag?: boolean;
  eval_provider?: string;
  answer_source?: 'text' | 'video' | 'audio';
  recording_url?: string | null;
  transcription_confidence?: number | null;
  transcription_mode?: 'real' | 'fallback' | null;
}

export interface ProctoringEvent {
  event_type: string;
  severity: 'low' | 'medium' | 'high';
  timestamp: string;
  formatted_timestamp?: string | null;
  question_id?: string | null;
  details?: string | null;
  screenshot_url?: string | null;
}

export interface ProctoringFrameResponse {
  person_count?: number | null;
  face_count?: number | null;
  phone_detected?: boolean;
  phone_count?: number;
  event_logged?: string | null;
  severity?: string | null;
  screenshot_url?: string | null;
  success: boolean;
  error?: string | null;
}

export interface CompleteSessionResponse {
  session_id: string;
  status: string;
  overall_score: number;
  integrity_score?: number | null;
  integrity_flags?: string[];
}

export interface FullReportResponse {
  session_id: string;
  candidate_name: string;
  candidate_email: string;
  job_role: string;
  status: string;
  interview_mode?: 'live' | 'async';
  answer_capture_type?: 'text' | 'video';
  session_deadline?: string | null;
  interviewer_photo_url?: string | null;
  last_active_at?: string | null;
  overall_score: number | null;
  integrity_score?: number | null;
  integrity_flags?: string[];
  proctoring_events?: ProctoringEvent[];
  session_video_url?: string | null;
  eval_provider?: string;
  created_at: string;
  completed_at?: string | null;
  report: Report | null;
  transcript: TranscriptItem[];
  mock?: boolean;
}

export interface SessionCreateResponse {
  session_id: string;
  candidate_id: string;
  candidate_name: string;
  total_questions: number;
  session_url: string;
  interview_mode?: 'live' | 'async';
  answer_capture_type?: 'text' | 'video';
  session_deadline?: string | null;
  interviewer_photo_url?: string | null;
  position?: string;
  email_sent?: boolean;
  email_subject?: string | null;
  email_body?: string | null;
  mock?: boolean;
}

export interface SessionListItem {
  id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  status: 'pending' | 'in_progress' | 'completed' | 'expired' | 'abandoned';
  interview_mode?: 'live' | 'async';
  answer_capture_type?: 'text' | 'video';
  session_deadline?: string | null;
  last_active_at?: string | null;
  overall_score: number | null;
  integrity_score?: number | null;
  created_at: string;
  completed_at?: string | null;
  total_questions: number;
  answered_questions: number;
}

