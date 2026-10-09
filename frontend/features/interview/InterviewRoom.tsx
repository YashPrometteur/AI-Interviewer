'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '../../lib/api';
import { Question, AnswerEvaluation, SessionQuestionItem } from '../../lib/types';
import { QuestionCard } from './QuestionCard';
import { AnswerInput } from './AnswerInput';
import { AnswerRecorder } from './AnswerRecorder';
import { ProctoringMonitor } from '../proctoring/ProctoringMonitor';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';

interface InterviewRoomProps {
  sessionId: string;
}

export const InterviewRoom: React.FC<InterviewRoomProps> = ({ sessionId }) => {
  const router = useRouter();

  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);
  const [allQuestionsList, setAllQuestionsList] = useState<SessionQuestionItem[]>([]);
  const [questionNumber, setQuestionNumber] = useState(1);
  const [totalQuestions, setTotalQuestions] = useState(3);
  const [remainingQuestionsCount, setRemainingQuestionsCount] = useState<number>(3);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);
  const [isMockSession, setIsMockSession] = useState(false);
  const [lastEvaluation, setLastEvaluation] = useState<AnswerEvaluation | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [interviewMode, setInterviewMode] = useState<'live' | 'async'>('live');
  const [answerCaptureType, setAnswerCaptureType] = useState<'text' | 'video'>('video');
  const [sessionDeadline, setSessionDeadline] = useState<string | null>(null);
  const [activeCaptureMode, setActiveCaptureMode] = useState<'text' | 'video'>('video');
  const [sessionElapsedSeconds, setSessionElapsedSeconds] = useState(0);

  // In-flight background answer evaluations (for question-wise transcripts)
  const pendingEvaluationsRef = useRef<Promise<any>[]>([]);

  // Real-time proctoring malpractice warning state
  const [activeWarning, setActiveWarning] = useState<{
    title: string;
    message: string;
    severity: 'low' | 'medium' | 'high';
  } | null>(null);
  const warningTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleProctoringWarning = useCallback((w: { title: string; message: string; severity: 'low' | 'medium' | 'high' }) => {
    setActiveWarning(w);
    if (warningTimeoutRef.current) clearTimeout(warningTimeoutRef.current);
    const duration = w.severity === 'high' ? 12000 : w.severity === 'medium' ? 8000 : 5000;
    warningTimeoutRef.current = setTimeout(() => {
      setActiveWarning(null);
    }, duration);
  }, []);

  // Live total session elapsed timer tick
  useEffect(() => {
    if (interviewMode === 'live' && !isCompleting) {
      const interval = setInterval(() => {
        setSessionElapsedSeconds((prev) => prev + 1);
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [interviewMode, isCompleting]);

  const refreshQuestionsList = useCallback(async () => {
    try {
      const data = await api.getSessionQuestions(sessionId);
      if (data && data.questions) {
        setAllQuestionsList(data.questions);
        setTotalQuestions(data.total_questions);
      }
    } catch (e) {
      console.warn('[InterviewRoom] Could not load questions list:', e);
    }
  }, [sessionId]);

  const fetchQuestion = useCallback(async (retryCount = 0) => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const res = await api.getNextQuestion(sessionId);

      if (res.mock) {
        setIsMockSession(true);
      }

      if (res.interview_mode) {
        setInterviewMode(res.interview_mode);
      }
      if (res.answer_capture_type) {
        setAnswerCaptureType(res.answer_capture_type);
        setActiveCaptureMode(res.answer_capture_type);
      }
      if (res.session_deadline) {
        setSessionDeadline(res.session_deadline);
      }

      if (res.is_completed || !res.question) {
        // All questions completed, finalize interview
        await handleFinishSession();
        return;
      }

      setCurrentQuestion(res.question);
      setRemainingQuestionsCount(res.remaining_count);
      const qNum = res.question.order_index != null ? res.question.order_index + 1 : 1;
      setQuestionNumber(qNum);
      if (res.question.mock) setIsMockSession(true);
      setTotalQuestions((prev) => Math.max(prev, qNum + res.remaining_count - 1));
      await refreshQuestionsList();
      setIsLoading(false);
    } catch (err: any) {
      if (retryCount < 3) {
        setTimeout(() => fetchQuestion(retryCount + 1), 2000);
      } else {
        setErrorMessage(err.message || 'Error fetching next question.');
        setIsLoading(false);
      }
    }
  }, [sessionId, refreshQuestionsList]);

  useEffect(() => {
    if (sessionId) {
      fetchQuestion();
    }
  }, [sessionId, fetchQuestion]);

  // Maneuver directly to a specific question
  const handleSelectQuestion = async (targetQId: string) => {
    if (currentQuestion?.id === targetQId) return;
    try {
      setIsLoading(true);
      setErrorMessage(null);
      setLastEvaluation(null);
      const q = await api.getSessionQuestionById(sessionId, targetQId);
      setCurrentQuestion(q);
      const qIndex = allQuestionsList.findIndex((item) => item.id === targetQId);
      setQuestionNumber(qIndex !== -1 ? qIndex + 1 : (q.order_index != null ? q.order_index + 1 : 1));
      if (q.mock) setIsMockSession(true);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to switch question.');
    } finally {
      setIsLoading(false);
    }
  };

  // Video Mode: Question-Wise submission
  const handleContinuousQuestionSubmit = useCallback(async (chunkBlob: Blob, questionId: string) => {
    try {
      const res = await api.submitAnswerRecording(sessionId, questionId, chunkBlob);
      console.log(`[InterviewRoom] Evaluated Q: ${questionId}`, res);
      await refreshQuestionsList();
    } catch (err: any) {
      console.error('[InterviewRoom] Submit question error:', err);
    }
  }, [sessionId, refreshQuestionsList]);

  // Video Mode: Advance to next question seamlessly without unmounting camera
  const handleAdvanceToNextQuestion = useCallback(async () => {
    try {
      setErrorMessage(null);
      const currentQId = currentQuestion?.id;
      const res = await api.getNextQuestion(sessionId, currentQId);

      if (res.is_completed || !res.question) {
        // Finalize interview if no more questions
        await handleFinishSession();
        return;
      }

      setCurrentQuestion(res.question);
      if (res.question.order_index != null) {
        setQuestionNumber(res.question.order_index + 1);
      } else {
        setQuestionNumber((prev) => prev + 1);
      }
      setRemainingQuestionsCount(res.remaining_count);
      if (res.question.mock) setIsMockSession(true);
      await refreshQuestionsList();
    } catch (err: any) {
      setErrorMessage(err.message || 'Error advancing to next question.');
    }
  }, [sessionId, currentQuestion, refreshQuestionsList]);

  // Video Mode: Finalize master session video upload and finish session
  const handleFinishMasterSession = useCallback(async (masterBlob: Blob) => {
    try {
      setIsCompleting(true);

      // 1. Wait for any in-flight background evaluations to settle so transcripts are written to MongoDB
      if (pendingEvaluationsRef.current.length > 0) {
        await Promise.allSettled(pendingEvaluationsRef.current);
      }

      // 2. Upload the complete continuous master session video (10 minutes)
      try {
        await api.uploadSessionVideo(sessionId, masterBlob);
      } catch (uploadErr) {
        console.warn('[InterviewRoom] Master video upload failed:', uploadErr);
      }

      // 3. Mark session complete & generate comprehensive scorecard in MongoDB
      await api.completeSession(sessionId);

      // 4. Redirect to candidate evaluation report
      router.push(`/reports?session_id=${sessionId}`);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to complete interview session.');
      setIsCompleting(false);
    }
  }, [router, sessionId]);

  // Text Mode submission
  const handleTextAnswerSubmit = async (answerText: string) => {
    if (!currentQuestion) return;
    try {
      setIsSubmitting(true);
      setErrorMessage(null);
      const evalRes = await api.submitAnswer(sessionId, currentQuestion.id, answerText);
      if (evalRes.mock) setIsMockSession(true);
      setLastEvaluation(evalRes);
    } catch (err: any) {
      setErrorMessage(err.message || 'Error evaluating answer.');
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNextTurnTextMode = async () => {
    setLastEvaluation(null);
    setErrorMessage(null);
    const currentQId = currentQuestion?.id;
    try {
      setIsLoading(true);
      const res = await api.getNextQuestion(sessionId, currentQId);
      if (res.is_completed || !res.question) {
        await handleFinishSession();
        return;
      }
      setCurrentQuestion(res.question);
      if (res.question.order_index != null) {
        setQuestionNumber(res.question.order_index + 1);
      } else {
        setQuestionNumber((prev) => prev + 1);
      }
      setRemainingQuestionsCount(res.remaining_count);
      if (res.question.mock) setIsMockSession(true);
    } catch (err: any) {
      setErrorMessage(err.message || 'Error fetching next question.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleFinishSession = async () => {
    try {
      setIsCompleting(true);
      if (pendingEvaluationsRef.current.length > 0) {
        await Promise.allSettled(pendingEvaluationsRef.current);
      }
      await api.completeSession(sessionId);
      router.push(`/reports?session_id=${sessionId}`);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to complete session.');
      setIsCompleting(false);
    }
  };

  const handleSaveAndContinueLater = () => {
    router.push('/');
  };

  const formatTimer = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDeadline = (isoString: string | null) => {
    if (!isoString) return 'No deadline';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  const isLastQuestion = questionNumber >= totalQuestions || remainingQuestionsCount <= 1;

  if (isCompleting) {
    return (
      <div style={{ maxWidth: '700px', margin: '4rem auto', textAlign: 'center', padding: '2rem' }}>
        <Card>
          <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>📊</div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
            Finalizing Interview & Saving Full Recording...
          </h2>
          <p style={{ color: '#64748b', marginBottom: '1.5rem', lineHeight: 1.5 }}>
            Synthesizing question-wise voice transcripts, evaluating technical competency scores, saving evidence telemetry, and compiling the candidate report.
          </p>
          <div style={{
            display: 'inline-block',
            width: '32px',
            height: '32px',
            border: '3px solid #e2e8f0',
            borderTopColor: '#2563eb',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }} />
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div style={{ maxWidth: '700px', margin: '4rem auto', textAlign: 'center', padding: '2rem' }}>
        <Card>
          <div style={{
            display: 'inline-block',
            width: '28px',
            height: '28px',
            border: '3px solid #e2e8f0',
            borderTopColor: '#2563eb',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            marginBottom: '0.75rem',
          }} />
          <p style={{ color: '#64748b', margin: '0 0 1rem 0' }}>Loading interview questions...</p>
          <button
            type="button"
            onClick={() => fetchQuestion(0)}
            style={{
              padding: '0.4rem 0.9rem',
              fontSize: '0.8rem',
              fontWeight: 600,
              backgroundColor: '#f1f5f9',
              color: '#334155',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            🔄 Reload Question
          </button>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '850px', margin: '2rem auto', padding: '0 1rem' }}>
      {/* Background Proctoring Telemetry (tracks tab switch, focus loss, screenshot evidence) */}
      <ProctoringMonitor
        sessionId={sessionId}
        activeQuestionId={currentQuestion?.id}
        isActive={!isCompleting}
        onWarning={handleProctoringWarning}
      />

      {/* Live Proctoring Malpractice Warning Banner */}
      {activeWarning && (
        <div style={{
          marginBottom: '1.25rem',
          padding: '0.9rem 1.25rem',
          borderRadius: '10px',
          backgroundColor: activeWarning.severity === 'high' ? '#fee2e2' : '#fffbeb',
          border: activeWarning.severity === 'high' ? '2px solid #ef4444' : '2px solid #f59e0b',
          color: activeWarning.severity === 'high' ? '#991b1b' : '#92400e',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.1)',
          transition: 'all 0.3s ease',
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.4rem', lineHeight: 1 }}>
              {activeWarning.severity === 'high' ? '🚨' : '⚠️'}
            </span>
            <div>
              <div style={{ fontWeight: 800, fontSize: '0.95rem', marginBottom: '0.15rem' }}>
                {activeWarning.title}
              </div>
              <div style={{ fontSize: '0.85rem', opacity: 0.95, lineHeight: 1.4 }}>
                {activeWarning.message}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setActiveWarning(null)}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.25rem',
              cursor: 'pointer',
              color: 'inherit',
              padding: '0.25rem 0.5rem',
              opacity: 0.7,
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Top Banner with Mode & Session Info */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1.5rem',
        padding: '0.75rem 1.25rem',
        backgroundColor: '#ffffff',
        borderRadius: '10px',
        border: '1px solid #e2e8f0',
        flexWrap: 'wrap',
        gap: '0.5rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {interviewMode === 'async' ? (
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              backgroundColor: '#ede9fe',
              color: '#6d28d9',
              padding: '0.25rem 0.6rem',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: 700,
            }}>
              📅 ASYNC INTERVIEW
            </span>
          ) : (
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              backgroundColor: '#ecfdf5',
              color: '#047857',
              padding: '0.25rem 0.6rem',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: 700,
            }}>
              ⏱️ LIVE SESSION ({formatTimer(sessionElapsedSeconds)} / 10:00)
            </span>
          )}

          <span style={{ fontSize: '0.8rem', color: '#64748b', fontFamily: 'monospace' }}>
            Session: {sessionId.slice(0, 8)}...
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {interviewMode === 'async' && sessionDeadline && (
            <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
              ⏳ Deadline: <strong>{formatDeadline(sessionDeadline)}</strong>
            </span>
          )}

          {interviewMode === 'async' && (
            <Button
              variant="secondary"
              onClick={handleSaveAndContinueLater}
              style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
            >
              💾 Save & Continue Later
            </Button>
          )}

          {isMockSession && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              backgroundColor: '#fef3c7',
              border: '1px solid #fde68a',
              padding: '0.25rem 0.6rem',
              borderRadius: '6px',
              fontSize: '0.75rem',
              fontWeight: 700,
              color: '#b45309',
            }}>
              <span>⚠️</span> MOCK MODE ACTIVE
            </div>
          )}
        </div>
      </div>

      {errorMessage && (
        <div style={{
          marginBottom: '1rem',
          padding: '0.75rem 1rem',
          backgroundColor: '#fee2e2',
          color: '#b91c1c',
          borderRadius: '8px',
          fontSize: '0.9rem',
        }}>
          ⚠️ {errorMessage}
        </div>
      )}

      {/* Text Mode Turn Evaluation Feedback Card */}
      {lastEvaluation && activeCaptureMode === 'text' && (
        <Card style={{ marginBottom: '1.5rem', backgroundColor: '#f8fafc', borderLeft: '4px solid #10b981' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '1.1rem' }}>✅</span>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#0f172a' }}>
                Turn Evaluation Recorded
              </h3>
            </div>
            <div style={{
              fontSize: '1rem',
              fontWeight: 800,
              padding: '0.3rem 0.8rem',
              borderRadius: '9999px',
              backgroundColor: lastEvaluation.score >= 7 ? '#dcfce7' : lastEvaluation.score >= 5 ? '#fef3c7' : '#fee2e2',
              color: lastEvaluation.score >= 7 ? '#15803d' : lastEvaluation.score >= 5 ? '#b45309' : '#b91c1c',
            }}>
              Score: {lastEvaluation.score.toFixed(1)} / 10
            </div>
          </div>

          <p style={{ color: '#334155', fontSize: '0.95rem', lineHeight: 1.5, margin: '0 0 1rem 0' }}>
            <strong>AI Feedback:</strong> {lastEvaluation.reasoning}
          </p>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button variant="primary" onClick={handleNextTurnTextMode}>
              Proceed to Next Question →
            </Button>
          </div>
        </Card>
      )}

      {/* Active Question Display & Navigation Maneuver Bar */}
      {currentQuestion && (!lastEvaluation || activeCaptureMode === 'video') && (
        <>
          {/* Question Maneuver & Navigation Bar */}
          {allQuestionsList.length > 0 && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              padding: '0.65rem 1rem',
              marginBottom: '1rem',
              gap: '0.75rem',
              flexWrap: 'wrap',
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{
                  fontSize: '0.75rem',
                  fontWeight: 800,
                  color: '#64748b',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}>
                  Jump to Question:
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                  {allQuestionsList.map((item, idx) => {
                    const isSelected = item.id === currentQuestion?.id;
                    const num = item.order_index != null ? item.order_index + 1 : idx + 1;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => handleSelectQuestion(item.id)}
                        title={`Question ${num}: ${item.skill_tag || 'Interview Question'} (${item.difficulty || 'Medium'})`}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.3rem',
                          padding: '0.3rem 0.65rem',
                          fontSize: '0.8rem',
                          fontWeight: isSelected ? 700 : 600,
                          borderRadius: '8px',
                          border: isSelected
                            ? '1.5px solid #2563eb'
                            : item.is_answered
                            ? '1px solid #86efac'
                            : '1px solid #cbd5e1',
                          backgroundColor: isSelected
                            ? '#2563eb'
                            : item.is_answered
                            ? '#f0fdf4'
                            : '#f8fafc',
                          color: isSelected
                            ? '#ffffff'
                            : item.is_answered
                            ? '#166534'
                            : '#475569',
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                          boxShadow: isSelected ? '0 2px 6px rgba(37, 99, 235, 0.35)' : 'none',
                        }}
                      >
                        {item.is_answered && !isSelected && <span style={{ color: '#16a34a' }}>✓</span>}
                        {isSelected && <span style={{ fontSize: '0.7rem' }}>●</span>}
                        <span>Q{num}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Step Navigation Prev / Next */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                {(() => {
                  const currIdx = allQuestionsList.findIndex((q) => q.id === currentQuestion?.id);
                  const canGoPrev = currIdx > 0;
                  const canGoNext = currIdx >= 0 && currIdx < allQuestionsList.length - 1;
                  return (
                    <>
                      <button
                        type="button"
                        disabled={!canGoPrev}
                        onClick={() => {
                          if (canGoPrev) handleSelectQuestion(allQuestionsList[currIdx - 1].id);
                        }}
                        style={{
                          padding: '0.3rem 0.6rem',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          backgroundColor: canGoPrev ? '#f1f5f9' : '#f8fafc',
                          color: canGoPrev ? '#334155' : '#cbd5e1',
                          border: '1px solid #cbd5e1',
                          borderRadius: '6px',
                          cursor: canGoPrev ? 'pointer' : 'not-allowed',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        ← Prev
                      </button>
                      <button
                        type="button"
                        disabled={!canGoNext}
                        onClick={() => {
                          if (canGoNext) handleSelectQuestion(allQuestionsList[currIdx + 1].id);
                        }}
                        style={{
                          padding: '0.3rem 0.6rem',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          backgroundColor: canGoNext ? '#f1f5f9' : '#f8fafc',
                          color: canGoNext ? '#334155' : '#cbd5e1',
                          border: '1px solid #cbd5e1',
                          borderRadius: '6px',
                          cursor: canGoNext ? 'pointer' : 'not-allowed',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        Next →
                      </button>
                    </>
                  );
                })()}
              </div>
            </div>
          )}

          <QuestionCard
            question={currentQuestion}
            questionNumber={questionNumber}
            totalQuestions={totalQuestions}
          />

          {activeCaptureMode === 'video' ? (
            <AnswerRecorder
              sessionId={sessionId}
              activeQuestionId={currentQuestion.id}
              questionText={currentQuestion.text}
              questionDifficulty={currentQuestion.difficulty}
              questionNumber={questionNumber}
              totalQuestions={totalQuestions}
              isLastQuestion={isLastQuestion}
              onSubmitQuestionAnswer={handleContinuousQuestionSubmit}
              onAdvanceQuestion={handleAdvanceToNextQuestion}
              onFinishMasterSession={handleFinishMasterSession}
              onSwitchToText={() => setActiveCaptureMode('text')}
              onWarning={handleProctoringWarning}
              isLoading={isSubmitting}
            />
          ) : (
            <>
              <AnswerInput onSubmit={handleTextAnswerSubmit} isLoading={isSubmitting} />
              {answerCaptureType === 'video' && (
                <div style={{ marginTop: '0.75rem', textAlign: 'center' }}>
                  <button
                    type="button"
                    onClick={() => setActiveCaptureMode('video')}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#2563eb',
                      fontSize: '0.875rem',
                      cursor: 'pointer',
                      textDecoration: 'underline',
                    }}
                  >
                    📹 Switch back to Video Recording Mode
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
};
