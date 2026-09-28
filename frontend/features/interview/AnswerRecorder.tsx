'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Button } from '../../components/Button';
import { api } from '../../lib/api';

interface AnswerRecorderProps {
  sessionId: string;
  activeQuestionId: string;
  questionDifficulty?: 'easy' | 'medium' | 'hard' | string;
  questionNumber: number;
  totalQuestions: number;
  isLastQuestion: boolean;
  onSubmitQuestionAnswer: (chunkBlob: Blob, questionId: string) => Promise<void>;
  onAdvanceQuestion: () => Promise<void>;
  onFinishMasterSession: (masterBlob: Blob) => Promise<void>;
  onSwitchToText?: () => void;
  onWarning?: (warning: { title: string; message: string; severity: 'low' | 'medium' | 'high' }) => void;
  isLoading?: boolean;
}

/**
 * Difficulty duration mapping requested by user:
 * - Easy: 2 minutes (120s)
 * - Medium: 3 minutes (180s)
 * - Hard: 5 minutes (300s)
 * Total continuous session cap: ~10 minutes (600s)
 */
export const getDurationForDifficulty = (difficulty?: string): number => {
  switch ((difficulty || '').toLowerCase().trim()) {
    case 'easy':
      return 120; // 2 minutes
    case 'medium':
      return 180; // 3 minutes
    case 'hard':
      return 300; // 5 minutes
    default:
      return 120; // default 2 minutes
  }
};

export const AnswerRecorder: React.FC<AnswerRecorderProps> = ({
  sessionId,
  activeQuestionId,
  questionDifficulty = 'easy',
  questionNumber,
  totalQuestions,
  isLastQuestion,
  onSubmitQuestionAnswer,
  onAdvanceQuestion,
  onFinishMasterSession,
  onSwitchToText,
  onWarning,
  isLoading = false,
}) => {
  // Media streams & active recorder states
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [sessionStatus, setSessionStatus] = useState<'ready' | 'recording' | 'finalizing'>('ready');
  const [faceStatus, setFaceStatus] = useState<'detecting' | 'ok' | 'no_face' | 'multiple_faces'>('detecting');
  const [audioLevel, setAudioLevel] = useState<number>(0);

  // Timers: per-question countdown + total session elapsed
  const duration = getDurationForDifficulty(questionDifficulty);
  const [questionRemainingSeconds, setQuestionRemainingSeconds] = useState<number>(duration);
  const [questionTotalSeconds, setQuestionTotalSeconds] = useState<number>(duration);
  const [sessionElapsedSeconds, setSessionElapsedSeconds] = useState<number>(0);

  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // References to keep media continuous across question transitions
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Master Session Recorder (runs continuously for the full 10-minute session)
  const masterRecorderRef = useRef<MediaRecorder | null>(null);
  const masterChunksRef = useRef<Blob[]>([]);

  // Question-Wise Recorder (sliced per question)
  const questionRecorderRef = useRef<MediaRecorder | null>(null);
  const questionChunksRef = useRef<Blob[]>([]);
  const currentRecordingQIdRef = useRef<string>(activeQuestionId);

  // Interval & Telemetry Refs
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const frameSamplingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const silenceCounterRef = useRef<number>(0);
  const isTransitioningRef = useRef<boolean>(false);

  // Synchronized refs to avoid re-creating callbacks and triggering effect teardowns
  const sessionIdRef = useRef(sessionId);
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

  const activeQuestionIdRef = useRef(activeQuestionId);
  useEffect(() => { activeQuestionIdRef.current = activeQuestionId; }, [activeQuestionId]);

  const onWarningRef = useRef(onWarning);
  useEffect(() => { onWarningRef.current = onWarning; }, [onWarning]);

  const isLastQuestionRef = useRef(isLastQuestion);
  useEffect(() => { isLastQuestionRef.current = isLastQuestion; }, [isLastQuestion]);

  const onSubmitQuestionAnswerRef = useRef(onSubmitQuestionAnswer);
  useEffect(() => { onSubmitQuestionAnswerRef.current = onSubmitQuestionAnswer; }, [onSubmitQuestionAnswer]);

  const onAdvanceQuestionRef = useRef(onAdvanceQuestion);
  useEffect(() => { onAdvanceQuestionRef.current = onAdvanceQuestion; }, [onAdvanceQuestion]);

  const onFinishMasterSessionRef = useRef(onFinishMasterSession);
  useEffect(() => { onFinishMasterSessionRef.current = onFinishMasterSession; }, [onFinishMasterSession]);

  const questionNumberRef = useRef(questionNumber);
  useEffect(() => { questionNumberRef.current = questionNumber; }, [questionNumber]);

  // Determine supported mimeType once
  const getSupportedMimeType = () => {
    const candidates = [
      'video/webm;codecs=vp8,opus',
      'video/webm;codecs=vp9,opus',
      'video/webm',
      'video/mp4',
    ];
    for (const mime of candidates) {
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mime)) {
        return mime;
      }
    }
    return '';
  };

  // Helper to attach stream to video element
  const attachStreamToVideo = useCallback((mediaStream: MediaStream) => {
    if (videoPreviewRef.current) {
      if (videoPreviewRef.current.srcObject !== mediaStream) {
        videoPreviewRef.current.srcObject = mediaStream;
      }
      videoPreviewRef.current.play().catch((e) => {
        console.warn('[AnswerRecorder] Video auto-play error:', e);
      });
    }
  }, []);

  // Frame sampling helper (captures a snapshot to JPEG and analyzes via CV proctoring)
  const sampleFrame = useCallback(async () => {
    const currentSessionId = sessionIdRef.current;
    const currentQId = activeQuestionIdRef.current;
    if (!currentSessionId || !videoPreviewRef.current || videoPreviewRef.current.readyState < 2) return;
    try {
      if (!canvasRef.current) {
        canvasRef.current = document.createElement('canvas');
        canvasRef.current.width = 640;
        canvasRef.current.height = 360;
      }
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      ctx.drawImage(videoPreviewRef.current, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        async (blob) => {
          if (blob) {
            try {
              const res = await api.uploadProctoringFrame(currentSessionId, blob, currentQId);
              if (res && res.success) {
                if (res.event_logged === 'cell_phone_detected' || res.phone_detected) {
                  onWarningRef.current?.({
                    title: '🚨 Malpractice Warning: Mobile Phone Detected!',
                    message: 'Unauthorized mobile device/phone detected in camera frame. Electronic devices are strictly prohibited during the interview.',
                    severity: 'high',
                  });
                } else if (res.event_logged === 'multiple_faces_detected' || (res.person_count && res.person_count > 1) || (res.face_count && res.face_count > 1)) {
                  setFaceStatus('multiple_faces');
                  onWarningRef.current?.({
                    title: '🚨 Malpractice Warning: Multiple Faces Detected!',
                    message: `Multiple individuals (${res.person_count || 2}) detected in camera view. External presence is strictly prohibited.`,
                    severity: 'high',
                  });
                } else if (res.event_logged === 'no_face_detected' || res.person_count === 0 || res.face_count === 0) {
                  setFaceStatus('no_face');
                  onWarningRef.current?.({
                    title: '⚠️ Face Out of Frame!',
                    message: 'No candidate face detected in the camera frame. Please center yourself directly in front of the camera.',
                    severity: 'medium',
                  });
                } else {
                  setFaceStatus('ok');
                }
              }
            } catch (err) {
              console.warn('[Proctoring] Periodic frame sampling upload skipped:', err);
            }
          }
        },
        'image/jpeg',
        0.75
      );
    } catch (err) {
      console.warn('[Proctoring] Frame capture error:', err);
    }
  }, []);

  // Audio Telemetry (detects voice activity level & prolonged silence)
  const setupAudioTelemetry = useCallback((mediaStream: MediaStream) => {
    try {
      const audioTracks = mediaStream.getAudioTracks();
      if (audioTracks.length === 0) return;

      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioContextClass) return;

      const audioCtx = new AudioContextClass();
      audioContextRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(mediaStream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      silenceCounterRef.current = 0;

      audioIntervalRef.current = setInterval(async () => {
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const average = sum / dataArray.length;
        setAudioLevel(Math.min(100, Math.round((average / 128) * 100)));

        if (average < 2.0) {
          silenceCounterRef.current += 1;
          // Log suspicious silence if candidate remains silent > 20s
          if (silenceCounterRef.current === 20 && sessionIdRef.current) {
            try {
              await api.logProctoringEvent(sessionIdRef.current, {
                event_type: 'suspicious_silence',
                question_id: activeQuestionIdRef.current,
                details: 'Prolonged microphone silence detected during spoken interview response.',
              });
            } catch (e) {
              console.warn('[Proctoring] Silence telemetry failed:', e);
            }
          }
        } else {
          silenceCounterRef.current = 0;
        }
      }, 500);
    } catch (e) {
      console.warn('[AnswerRecorder] Web Audio setup skipped:', e);
    }
  }, []);

  // Initialize camera and microphone stream ONCE (continuous live stream)
  const initMediaStream = useCallback(async () => {
    try {
      setPermissionError(null);
      setErrorMessage(null);

      let userMedia: MediaStream;
      try {
        userMedia = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
          audio: { echoCancellation: true, noiseSuppression: true },
        });
      } catch (firstErr) {
        console.warn('[AnswerRecorder] HD constraints failed, falling back to basic stream:', firstErr);
        userMedia = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true,
        });
      }

      streamRef.current = userMedia;
      setStream(userMedia);
      attachStreamToVideo(userMedia);
      setupAudioTelemetry(userMedia);

      // Periodic vision proctoring frame sampling every 6s
      if (frameSamplingIntervalRef.current) clearInterval(frameSamplingIntervalRef.current);
      setTimeout(() => sampleFrame(), 1500);
      frameSamplingIntervalRef.current = setInterval(() => {
        sampleFrame();
      }, 6000);

    } catch (err: any) {
      console.error('[AnswerRecorder] Camera/Mic error:', err);
      setPermissionError(
        'Unable to access camera and microphone. Please ensure permissions are granted and no other application is locking your camera.'
      );
    }
  }, [attachStreamToVideo, sampleFrame, setupAudioTelemetry]);

  // Cleanup strictly on component unmount
  useEffect(() => {
    initMediaStream();
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (frameSamplingIntervalRef.current) clearInterval(frameSamplingIntervalRef.current);
      if (audioIntervalRef.current) clearInterval(audioIntervalRef.current);
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, [initMediaStream]);

  // Start question-wise audio slice recorder on the continuous stream
  const startQuestionAudioRecorder = useCallback((qId: string) => {
    if (!streamRef.current) return;
    try {
      const audioTracks = streamRef.current.getAudioTracks();
      if (audioTracks.length === 0) return;
      const audioStream = new MediaStream(audioTracks);

      let mimeType = 'audio/webm;codecs=opus';
      if (typeof MediaRecorder !== 'undefined' && !MediaRecorder.isTypeSupported(mimeType)) {
        if (MediaRecorder.isTypeSupported('audio/webm')) {
          mimeType = 'audio/webm';
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = 'audio/mp4';
        } else {
          mimeType = '';
        }
      }

      const qRecorder = mimeType
        ? new MediaRecorder(audioStream, { mimeType, audioBitsPerSecond: 128000 })
        : new MediaRecorder(audioStream, { audioBitsPerSecond: 128000 });
      questionChunksRef.current = [];
      currentRecordingQIdRef.current = qId;

      qRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          questionChunksRef.current.push(e.data);
        }
      };

      qRecorder.start(500); // 500ms chunks for rapid slicing
      questionRecorderRef.current = qRecorder;
    } catch (e: any) {
      console.error('[AnswerRecorder] Failed to start question audio slice recorder:', e);
    }
  }, []);

  // Finalize master session video and complete interview
  const triggerFinishSession = useCallback(async (sessionExpired: boolean) => {
    setSessionStatus('finalizing');
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (frameSamplingIntervalRef.current) {
      clearInterval(frameSamplingIntervalRef.current);
      frameSamplingIntervalRef.current = null;
    }
    if (audioIntervalRef.current) {
      clearInterval(audioIntervalRef.current);
      audioIntervalRef.current = null;
    }

    setStatusMessage(sessionExpired
      ? '10-minute session duration reached! Finalizing interview and saving complete video...'
      : 'All questions completed! Finalizing interview and saving complete video...'
    );

    const masterRecorder = masterRecorderRef.current;
    const finishMaster = async () => {
      const mimeType = getSupportedMimeType();
      const masterBlob = new Blob(masterChunksRef.current, { type: mimeType || 'video/webm' });
      try {
        await onFinishMasterSessionRef.current(masterBlob);
      } catch (err: any) {
        setErrorMessage(err.message || 'Error saving complete session video.');
      }
    };

    if (masterRecorder && masterRecorder.state !== 'inactive') {
      masterRecorder.onstop = () => {
        finishMaster();
      };
      masterRecorder.stop();
    } else {
      await finishMaster();
    }
  }, []);

  const triggerFinishSessionRef = useRef(triggerFinishSession);
  useEffect(() => {
    triggerFinishSessionRef.current = triggerFinishSession;
  }, [triggerFinishSession]);

  // Trigger question transition: stops current question chunk recorder and submits chunk
  const triggerQuestionTransition = useCallback(async () => {
    if (isTransitioningRef.current) return;
    isTransitioningRef.current = true;

    const qIdToSubmit = currentRecordingQIdRef.current;
    const qRecorder = questionRecorderRef.current;

    setStatusMessage(`Submitting Question ${questionNumberRef.current} answer & loading next...`);

    // Helper to package audio slice chunks into an audio Blob for Whisper
    const finishChunkAndSubmit = async () => {
      const chunkBlob = new Blob(questionChunksRef.current, { type: 'audio/webm' });
      questionChunksRef.current = [];

      try {
        // Dispatch background submission for this question's audio/video
        await onSubmitQuestionAnswerRef.current(chunkBlob, qIdToSubmit);
      } catch (err) {
        console.error(`[AnswerRecorder] Answer submission error for question ${qIdToSubmit}:`, err);
      }

      if (isLastQuestionRef.current) {
        // This was the final question: finalize master recording and complete session
        await triggerFinishSessionRef.current(false);
      } else {
        // Advance to next question
        await onAdvanceQuestionRef.current();
        // isTransitioningRef will be reset when the new activeQuestionId arrives
      }
    };

    if (qRecorder && qRecorder.state !== 'inactive') {
      qRecorder.onstop = () => {
        finishChunkAndSubmit();
      };
      qRecorder.stop();
    } else {
      await finishChunkAndSubmit();
    }
  }, []);

  const triggerQuestionTransitionRef = useRef(triggerQuestionTransition);
  useEffect(() => {
    triggerQuestionTransitionRef.current = triggerQuestionTransition;
  }, [triggerQuestionTransition]);

  // Dedicated active session timer: ticks session elapsed and question countdown continuously
  useEffect(() => {
    if (sessionStatus !== 'recording') return;

    const interval = setInterval(() => {
      // 1. Session total elapsed seconds (capped at 600s = 10 mins)
      setSessionElapsedSeconds((prev) => {
        const nextSessionSec = prev + 1;
        if (nextSessionSec >= 600) {
          triggerFinishSessionRef.current(true);
        }
        return nextSessionSec;
      });

      // 2. Per-question countdown
      setQuestionRemainingSeconds((prev) => {
        if (prev <= 1) {
          if (!isTransitioningRef.current) {
            triggerQuestionTransitionRef.current();
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    timerIntervalRef.current = interval;

    return () => {
      clearInterval(interval);
      if (timerIntervalRef.current === interval) {
        timerIntervalRef.current = null;
      }
    };
  }, [sessionStatus]);

  // Handler to start the full 10-minute continuous session recording
  const handleStartInterviewSession = () => {
    if (!streamRef.current) {
      setErrorMessage('Camera & microphone stream not ready.');
      return;
    }

    try {
      const mimeType = getSupportedMimeType();
      const options = mimeType ? { mimeType } : undefined;

      // 1. Start Continuous Master Session Recorder (records uninterrupted 10-minute video)
      masterChunksRef.current = [];
      const masterRecorder = new MediaRecorder(streamRef.current, options);
      masterRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          masterChunksRef.current.push(e.data);
        }
      };
      masterRecorder.start(1000);
      masterRecorderRef.current = masterRecorder;

      // 2. Start Question 1 Audio Slice Recorder (captures speech for Q1 transcript)
      startQuestionAudioRecorder(activeQuestionId);

      // 3. Reset per-question countdown and total elapsed timer
      const initialDur = getDurationForDifficulty(questionDifficulty);
      setQuestionTotalSeconds(initialDur);
      setQuestionRemainingSeconds(initialDur);
      setSessionElapsedSeconds(0);
      isTransitioningRef.current = false;
      setSessionStatus('recording');
      setStatusMessage(`Question 1 started (${initialDur / 60}m limit). Speak your answer clearly.`);
    } catch (err: any) {
      setErrorMessage(`Failed to start session recording: ${err.message}`);
    }
  };

  // Watch for question changes: when a new question arrives, seamlessly start its chunk recorder and reset question timer
  useEffect(() => {
    if (sessionStatus === 'recording' && activeQuestionId && activeQuestionId !== currentRecordingQIdRef.current) {
      currentRecordingQIdRef.current = activeQuestionId;
      const newDur = getDurationForDifficulty(questionDifficulty);
      setQuestionTotalSeconds(newDur);
      setQuestionRemainingSeconds(newDur);
      isTransitioningRef.current = false;

      // Start new question audio slice recorder immediately on the continuous audio track
      startQuestionAudioRecorder(activeQuestionId);
      setStatusMessage(`Question ${questionNumber} active (${newDur / 60}m timer). Camera continuous.`);
    }
  }, [activeQuestionId, questionDifficulty, questionNumber, sessionStatus, startQuestionAudioRecorder]);

  // Format time utility: MM:SS
  const formatTimer = (seconds: number) => {
    const mins = Math.floor(Math.max(0, seconds) / 60);
    const secs = Math.max(0, seconds) % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Calculate percentage of time remaining for dynamic progress bar
  const progressPercent = Math.max(0, Math.min(100, (questionRemainingSeconds / (questionTotalSeconds || 1)) * 100));

  // Determine progress bar color based on urgency (<30s = red, <60s = amber, else emerald)
  const progressBarColor =
    questionRemainingSeconds <= 20
      ? '#ef4444' // red
      : questionRemainingSeconds <= 45
      ? '#f59e0b' // amber
      : '#10b981'; // green

  return (
    <div style={{ marginTop: '1rem' }}>
      {/* Status / Transition Banner */}
      {statusMessage && (
        <div style={{
          marginBottom: '0.75rem',
          padding: '0.6rem 1rem',
          backgroundColor: '#f0fdf4',
          border: '1px solid #bbf7d0',
          color: '#166534',
          borderRadius: '8px',
          fontSize: '0.85rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          transition: 'all 0.3s ease',
        }}>
          <span>✨ {statusMessage}</span>
          {sessionStatus === 'recording' && (
            <span style={{ fontSize: '0.75rem', color: '#15803d', fontWeight: 600 }}>
              Live Camera Continuous
            </span>
          )}
        </div>
      )}

      {/* Main Continuous Video Stream Container */}
      <div style={{
        position: 'relative',
        width: '100%',
        maxWidth: '720px',
        margin: '0 auto',
        borderRadius: '14px',
        overflow: 'hidden',
        backgroundColor: '#0f172a',
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.2), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
        aspectRatio: '16/9',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {/* Continuous Mirrored Video Element */}
        <video
          ref={(el) => {
            videoPreviewRef.current = el;
            if (el && streamRef.current && el.srcObject !== streamRef.current) {
              el.srcObject = streamRef.current;
              el.play().catch(() => {});
            }
          }}
          autoPlay
          muted
          playsInline
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: 'scaleX(-1)', // Mirrored view
          }}
        />

        {/* Top-Left: Total Continuous 10-Min Session Indicator */}
        {sessionStatus === 'recording' && (
          <div style={{
            position: 'absolute',
            top: '0.85rem',
            left: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            backgroundColor: 'rgba(15, 23, 42, 0.82)',
            padding: '0.4rem 0.8rem',
            borderRadius: '20px',
            color: '#ffffff',
            fontSize: '0.8rem',
            fontWeight: 700,
            backdropFilter: 'blur(6px)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            zIndex: 10,
          }}>
            <span style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              backgroundColor: '#ef4444',
              display: 'inline-block',
              animation: 'pulse 1.2s infinite',
            }} />
            <span>SESSION: {formatTimer(sessionElapsedSeconds)} / 10:00</span>
          </div>
        )}

        {/* Top-Center: Per-Question Countdown Timer (2-5 min by difficulty) */}
        {sessionStatus === 'recording' && (
          <div style={{
            position: 'absolute',
            top: '0.85rem',
            left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            backgroundColor: questionRemainingSeconds <= 20 ? 'rgba(185, 28, 28, 0.9)' : 'rgba(15, 23, 42, 0.85)',
            padding: '0.35rem 1rem',
            borderRadius: '20px',
            color: '#ffffff',
            backdropFilter: 'blur(6px)',
            border: questionRemainingSeconds <= 20 ? '1px solid #ef4444' : '1px solid rgba(255, 255, 255, 0.15)',
            zIndex: 10,
            transition: 'background-color 0.3s ease',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontWeight: 800, fontSize: '0.95rem' }}>
              <span>⏳</span>
              <span>{formatTimer(questionRemainingSeconds)} remaining</span>
            </div>
            <div style={{ fontSize: '0.65rem', opacity: 0.85, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Q{questionNumber} • {questionDifficulty} ({questionTotalSeconds / 60}m) • Auto-advances at 00:00
            </div>
          </div>
        )}

        {/* Top-Right: Proctoring Vision Face Status */}
        {stream && (
          <div style={{
            position: 'absolute',
            top: '0.85rem',
            right: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            backgroundColor:
              faceStatus === 'multiple_faces'
                ? 'rgba(220, 38, 38, 0.92)'
                : faceStatus === 'no_face'
                ? 'rgba(217, 119, 6, 0.92)'
                : 'rgba(15, 23, 42, 0.82)',
            padding: '0.35rem 0.75rem',
            borderRadius: '20px',
            color: '#ffffff',
            fontSize: '0.78rem',
            fontWeight: 700,
            backdropFilter: 'blur(6px)',
            border:
              faceStatus === 'multiple_faces'
                ? '1px solid #ef4444'
                : faceStatus === 'no_face'
                ? '1px solid #f59e0b'
                : '1px solid rgba(255, 255, 255, 0.15)',
            zIndex: 10,
          }}>
            {faceStatus === 'multiple_faces' && <span>🚨 Multiple Faces</span>}
            {faceStatus === 'no_face' && <span>⚠️ Face Out of Frame</span>}
            {faceStatus === 'ok' && <span style={{ color: '#86efac' }}>🟢 Face Centered</span>}
            {faceStatus === 'detecting' && <span>🛡️ Proctor Active</span>}
          </div>
        )}

        {/* Bottom-Left: Microphone Activity Equalizer Dot */}
        {sessionStatus === 'recording' && (
          <div style={{
            position: 'absolute',
            bottom: '0.85rem',
            left: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            padding: '0.3rem 0.6rem',
            borderRadius: '12px',
            color: '#cbd5e1',
            fontSize: '0.75rem',
            zIndex: 10,
          }}>
            <span>🎙️</span>
            <div style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: audioLevel > 5 ? '#22c55e' : '#64748b',
              transform: `scale(${1 + (audioLevel / 100) * 0.8})`,
              transition: 'transform 0.1s ease',
            }} />
            <span>{audioLevel > 5 ? 'Speaking' : 'Mic active'}</span>
          </div>
        )}

        {/* Pre-Interview Ready Overlay */}
        {sessionStatus === 'ready' && !permissionError && (
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            textAlign: 'center',
            color: '#ffffff',
            backdropFilter: 'blur(4px)',
            zIndex: 20,
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>📹</div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem' }}>
              Camera & Microphone Connected
            </h3>
            <p style={{ fontSize: '0.875rem', color: '#cbd5e1', maxWidth: '460px', marginBottom: '1.5rem', lineHeight: 1.5 }}>
              Your camera will remain on continuously for the entire interview (~10 mins).
              Each question has a 2 to 5-minute timer based on difficulty and will auto-advance to the next question.
            </p>
            <Button
              variant="primary"
              onClick={handleStartInterviewSession}
              style={{
                padding: '0.85rem 2.25rem',
                fontSize: '1.05rem',
                backgroundColor: '#dc2626',
                borderColor: '#dc2626',
                fontWeight: 700,
                boxShadow: '0 4px 14px rgba(220, 38, 38, 0.4)',
              }}
            >
              🔴 Begin Interview (Start Question 1)
            </Button>
          </div>
        )}

        {/* Finalizing Overlay */}
        {sessionStatus === 'finalizing' && (
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            textAlign: 'center',
            color: '#ffffff',
            zIndex: 30,
          }}>
            <div style={{
              width: '36px',
              height: '36px',
              border: '3px solid #334155',
              borderTopColor: '#38bdf8',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
              marginBottom: '1rem',
            }} />
            <h4 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.5rem' }}>
              Saving Full 10-Minute Video Recording...
            </h4>
            <p style={{ fontSize: '0.85rem', color: '#94a3b8', maxWidth: '420px' }}>
              Uploading continuous interview video, compiling question-wise transcripts, and generating evaluation report.
            </p>
          </div>
        )}

        {/* Permission Error Overlay */}
        {permissionError && (
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.94)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            textAlign: 'center',
            color: '#ffffff',
            zIndex: 25,
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>📹🚫</div>
            <h4 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Camera & Microphone Access Required
            </h4>
            <p style={{ fontSize: '0.85rem', color: '#94a3b8', maxWidth: '450px', marginBottom: '1.25rem', lineHeight: 1.4 }}>
              {permissionError}
            </p>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <Button variant="secondary" onClick={initMediaStream}>
                🔄 Retry Permissions
              </Button>
              {onSwitchToText && (
                <Button variant="primary" onClick={onSwitchToText}>
                  ✍️ Switch to Text Answer
                </Button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Per-Question Dynamic Countdown Progress Bar */}
      {sessionStatus === 'recording' && (
        <div style={{
          maxWidth: '720px',
          margin: '0.5rem auto 0 auto',
          backgroundColor: '#e2e8f0',
          height: '6px',
          borderRadius: '9999px',
          overflow: 'hidden',
          boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.1)',
        }}>
          <div style={{
            height: '100%',
            width: `${progressPercent}%`,
            backgroundColor: progressBarColor,
            transition: 'width 1s linear, background-color 0.5s ease',
          }} />
        </div>
      )}

      {/* Error Banner */}
      {errorMessage && (
        <div style={{
          marginTop: '0.75rem',
          padding: '0.75rem 1rem',
          backgroundColor: '#fee2e2',
          color: '#b91c1c',
          borderRadius: '8px',
          fontSize: '0.875rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}>
          ⚠️ {errorMessage}
        </div>
      )}

      {/* Control Bar: Switch to Text vs Manual Advance / Done Button */}
      <div style={{
        marginTop: '1.25rem',
        maxWidth: '720px',
        margin: '1.25rem auto 0 auto',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '0.75rem',
      }}>
        <div>
          {onSwitchToText && (
            <Button
              type="button"
              variant="secondary"
              onClick={onSwitchToText}
              disabled={isLoading || sessionStatus === 'finalizing'}
              style={{ fontSize: '0.85rem' }}
            >
              ✍️ Switch to Text Mode
            </Button>
          )}
        </div>

        {sessionStatus === 'recording' && (
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <Button
              type="button"
              variant="primary"
              onClick={triggerQuestionTransition}
              disabled={isLoading || isTransitioningRef.current}
              style={{
                padding: '0.75rem 1.75rem',
                fontSize: '0.95rem',
                fontWeight: 700,
                backgroundColor: isLastQuestion ? '#059669' : '#2563eb',
                borderColor: isLastQuestion ? '#059669' : '#2563eb',
              }}
            >
              {isLastQuestion
                ? '🏁 Done Answering & Finish Interview'
                : 'Done Answering & Answer Next Question →'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
