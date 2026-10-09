'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Button } from '../../components/Button';
import { api } from '../../lib/api';

interface AnswerRecorderProps {
  sessionId: string;
  activeQuestionId: string;
  questionText?: string;
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
 * 4-Pillar Adaptive Linguistic & Silence Analyzer
 * Computes dynamic silence thresholds based on spoken syntax, explicit conclusion cues, and question depth.
 */
export interface AdaptiveSilenceConfig {
  pattern: 'explicit_conclusion' | 'standard_complete' | 'dangling_conjunction' | 'empty';
  silenceWindowMs: number;
  reason: string;
}

export const analyzeSpokenThought = (
  transcript: string,
  questionText?: string
): AdaptiveSilenceConfig => {
  const clean = transcript.trim();
  if (!clean || clean.length < 3) {
    return {
      pattern: 'empty',
      silenceWindowMs: 12000,
      reason: 'Awaiting candidate spoken response',
    };
  }

  // Pillar 1: Explicit Conclusion Cues (2.0s quick response)
  const conclusionRegex = /\b(that'?s (all|it|everything|basically it|my answer|pretty much it)|i'?m done|that covers it|i don'?t know|i don'?t remember|nothing (more|else) to add|pass|skip|that wraps (it|things) up|that is all|that's about it)\b[\s\.\?!]*$/i;
  if (conclusionRegex.test(clean)) {
    return {
      pattern: 'explicit_conclusion',
      silenceWindowMs: 2000,
      reason: 'Explicit conclusion marker detected',
    };
  }

  // Pillar 1: Dangling Conjunctions & Filler Continuations (6.5s patient thinking buffer)
  const danglingRegex = /\b(and|because|also|so if|for example|for instance|in addition|furthermore|like|such as|whereas|while|meaning that|which is|then|or|but|plus|on top of that)\s*[\.,]*$/i;
  if (danglingRegex.test(clean)) {
    return {
      pattern: 'dangling_conjunction',
      silenceWindowMs: 6500,
      reason: 'Dangling conjunction or mid-sentence formulation',
    };
  }

  // Pillar 2: Multi-Part Question Depth Tracking (adds +2.0s buffer if response is brief)
  const wordCount = clean.split(/\s+/).filter(Boolean).length;
  const isMultiPartQuestion = Boolean(
    questionText &&
    (questionText.includes(' and ') ||
      questionText.includes('compare') ||
      questionText.includes('difference') ||
      questionText.includes('how does') ||
      questionText.includes('why is') ||
      questionText.includes('explain'))
  );

  if (isMultiPartQuestion && wordCount < 18) {
    return {
      pattern: 'standard_complete',
      silenceWindowMs: 6500,
      reason: 'Multi-part question requiring candidate elaboration time',
    };
  }

  // Pillar 1: Standard Complete Thought (4.5s relaxed thinking buffer)
  return {
    pattern: 'standard_complete',
    silenceWindowMs: 4500,
    reason: 'Complete sentence formulation',
  };
};

/**
 * Difficulty duration mapping:
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
  questionText,
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
  const [phoneDetected, setPhoneDetected] = useState<boolean>(false);
  const [audioLevel, setAudioLevel] = useState<number>(0);

  // 4-Pillar Adaptive Auto-Submission State
  const [autoSubmitCountdown, setAutoSubmitCountdown] = useState<number | null>(null);
  const [spokenInsight, setSpokenInsight] = useState<string | null>(null);

  // Timers: per-question countdown + total session elapsed
  const duration = getDurationForDifficulty(questionDifficulty);
  const [questionRemainingSeconds, setQuestionRemainingSeconds] = useState<number>(duration);
  const [questionTotalSeconds, setQuestionTotalSeconds] = useState<number>(duration);
  const [sessionElapsedSeconds, setSessionElapsedSeconds] = useState<number>(0);
  const [thinkTimeRemaining, setThinkTimeRemaining] = useState<number | null>(30);

  const [permissionError, setPermissionError] = useState<string | null>(null);
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

  // Adaptive Silence & Live Transcription Refs
  const continuousSilenceMsRef = useRef<number>(0);
  const liveTranscriptRef = useRef<string>('');
  const autoSubmitIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const speechRecognitionRef = useRef<any>(null);
  const questionTextRef = useRef(questionText);
  useEffect(() => { questionTextRef.current = questionText; }, [questionText]);

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
                  setPhoneDetected(true);
                  onWarningRef.current?.({
                    title: '🚨 Mobile Phone Detected',
                    message: 'Mobile device detected in camera frame. Electronic devices are not permitted during the interview.',
                    severity: 'high',
                  });
                } else {
                  setPhoneDetected(false);
                  if (res.event_logged === 'multiple_faces_detected' || (res.person_count && res.person_count > 1) || (res.face_count && res.face_count > 1)) {
                    setFaceStatus('multiple_faces');
                    onWarningRef.current?.({
                      title: '🚨 Multiple Faces Detected',
                      message: `Multiple individuals (${res.person_count || 2}) detected in camera view.`,
                      severity: 'high',
                    });
                  } else if (res.event_logged === 'no_face_detected' || res.person_count === 0 || res.face_count === 0) {
                    setFaceStatus('no_face');
                    onWarningRef.current?.({
                      title: '⚠️ Face Out of Frame',
                      message: 'Please keep your face centered in the camera view.',
                      severity: 'medium',
                    });
                  } else {
                    setFaceStatus('ok');
                  }
                }
              }
            } catch (err) {
              console.warn('[Proctoring] Periodic frame sampling skipped:', err);
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

  // Cancel any active auto-submission countdown
  const cancelAutoSubmit = useCallback(() => {
    if (autoSubmitIntervalRef.current) {
      clearInterval(autoSubmitIntervalRef.current);
      autoSubmitIntervalRef.current = null;
    }
    setAutoSubmitCountdown(null);
    continuousSilenceMsRef.current = 0;
  }, []);

  // Soft-landing countdown runner (4 seconds countdown before auto-submitting)
  const startAutoSubmitCountdown = useCallback(() => {
    if (autoSubmitIntervalRef.current || isTransitioningRef.current) return;
    let remaining = 4;
    setAutoSubmitCountdown(remaining);

    autoSubmitIntervalRef.current = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        if (autoSubmitIntervalRef.current) {
          clearInterval(autoSubmitIntervalRef.current);
          autoSubmitIntervalRef.current = null;
        }
        setAutoSubmitCountdown(null);
        if (!isTransitioningRef.current) {
          triggerQuestionTransitionRef.current();
        }
      } else {
        setAutoSubmitCountdown(remaining);
      }
    }, 1000);
  }, []);

  // Initialize live Web Speech API recognition for real-time phrase analysis & silence resetting
  const initLiveSpeechRecognition = useCallback(() => {
    if (typeof window === 'undefined') return;
    const SpeechRecognitionClass =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionClass) return;

    try {
      if (speechRecognitionRef.current) {
        try {
          speechRecognitionRef.current.stop();
        } catch (e) {}
      }

      const recognition = new SpeechRecognitionClass();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onresult = (event: any) => {
        let fullTranscript = '';
        for (let i = 0; i < event.results.length; i++) {
          fullTranscript += event.results[i][0].transcript + ' ';
        }
        liveTranscriptRef.current = fullTranscript.trim();

        // Spoken words detected -> Candidate is actively speaking, reset silence & cancel pill
        continuousSilenceMsRef.current = 0;
        cancelAutoSubmit();

        // Analyze spoken pattern dynamically
        const analysis = analyzeSpokenThought(liveTranscriptRef.current, questionTextRef.current);
        setSpokenInsight(analysis.reason);
      };

      recognition.onerror = (event: any) => {
        if (event.error !== 'no-speech') {
          console.warn('[AnswerRecorder] Live speech recognition warning:', event.error);
        }
      };

      recognition.onend = () => {
        if (sessionStatus === 'recording' && !isTransitioningRef.current) {
          try {
            recognition.start();
          } catch (e) {
            // Already active
          }
        }
      };

      recognition.start();
      speechRecognitionRef.current = recognition;
    } catch (err) {
      console.warn('[AnswerRecorder] Web Speech Recognition init skipped:', err);
    }
  }, [cancelAutoSubmit, sessionStatus]);

  // Audio Telemetry (detects voice activity level, sub-vocal fillers & runs adaptive silence checks)
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
      continuousSilenceMsRef.current = 0;

      // High-frequency 200ms tick for responsive VAD and filler detection
      audioIntervalRef.current = setInterval(async () => {
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const average = sum / dataArray.length;
        setAudioLevel(Math.min(100, Math.round((average / 128) * 100)));

        // Pillar 3: Sub-Vocal / Filler Awareness ("Umm...", "Uh...", breath shifts)
        // Average >= 3.0 indicates candidate vocalization
        if (average >= 3.0) {
          continuousSilenceMsRef.current = 0;
          silenceCounterRef.current = 0;
          cancelAutoSubmit();
        } else {
          // Candidate in silence -> Increment silence counters
          silenceCounterRef.current += 1;
          continuousSilenceMsRef.current += 200;

          // Proctoring check for suspicious silence (>15 seconds without speaking)
          if (silenceCounterRef.current === 75 && sessionIdRef.current) {
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

          // Pillar 1 & 2: Dynamic Auto-Submission Evaluation
          // Only evaluate when candidate has formulated a spoken answer
          if (
            liveTranscriptRef.current.trim().length > 0 &&
            !isTransitioningRef.current
          ) {
            const analysis = analyzeSpokenThought(liveTranscriptRef.current, questionTextRef.current);
            if (continuousSilenceMsRef.current >= analysis.silenceWindowMs) {
              startAutoSubmitCountdown();
            }
          }
        }
      }, 200);
    } catch (e) {
      console.warn('[AnswerRecorder] Web Audio setup skipped:', e);
    }
  }, [cancelAutoSubmit, startAutoSubmitCountdown]);

  // Start question-wise audio slice recorder on the continuous stream
  const startQuestionAudioRecorder = useCallback((qId: string, customStream?: MediaStream) => {
    const activeStream = customStream || streamRef.current;
    if (!activeStream) return;
    try {
      const audioTracks = activeStream.getAudioTracks();
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

  // Start continuous recording immediately when stream is ready
  const startContinuousSession = useCallback((activeStream: MediaStream) => {
    try {
      const mimeType = getSupportedMimeType();
      const options = mimeType ? { mimeType } : undefined;

      // 1. Master continuous session recording
      masterChunksRef.current = [];
      const masterRecorder = new MediaRecorder(activeStream, options);
      masterRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          masterChunksRef.current.push(e.data);
        }
      };
      masterRecorder.start(1000);
      masterRecorderRef.current = masterRecorder;

      // 2. Question audio slice recorder
      startQuestionAudioRecorder(activeQuestionIdRef.current, activeStream);

      // 3. Timers & Live Speech Recognition
      const initialDur = getDurationForDifficulty(questionDifficulty);
      setQuestionTotalSeconds(initialDur);
      setQuestionRemainingSeconds(initialDur);
      setThinkTimeRemaining(30);
      setSessionElapsedSeconds(0);
      isTransitioningRef.current = false;
      setSessionStatus('recording');

      // Initialize live speech analyzer
      initLiveSpeechRecognition();
    } catch (err: any) {
      console.error('[AnswerRecorder] Error starting recording:', err);
    }
  }, [initLiveSpeechRecognition, questionDifficulty, startQuestionAudioRecorder]);

  // Initialize camera and microphone stream ONCE
  const initMediaStream = useCallback(async () => {
    try {
      setPermissionError(null);
      setErrorMessage(null);

      let userMedia: MediaStream;
      try {
        userMedia = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      } catch (firstErr) {
        console.warn('[AnswerRecorder] HD constraints failed, falling back to basic stream:', firstErr);
        userMedia = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      }

      streamRef.current = userMedia;
      setStream(userMedia);
      attachStreamToVideo(userMedia);
      setupAudioTelemetry(userMedia);

      // Auto-start recording immediately
      startContinuousSession(userMedia);

      // Periodic vision proctoring frame sampling every 3s
      if (frameSamplingIntervalRef.current) clearInterval(frameSamplingIntervalRef.current);
      setTimeout(() => sampleFrame(), 1000);
      frameSamplingIntervalRef.current = setInterval(() => {
        sampleFrame();
      }, 3000);

    } catch (err: any) {
      console.error('[AnswerRecorder] Camera/Mic error:', err);
      setPermissionError(
        'Unable to access camera and microphone. Please ensure permissions are granted and no other application is locking your camera.'
      );
    }
  }, [attachStreamToVideo, sampleFrame, setupAudioTelemetry, startContinuousSession]);

  // Cleanup on unmount
  useEffect(() => {
    initMediaStream();
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (frameSamplingIntervalRef.current) clearInterval(frameSamplingIntervalRef.current);
      if (audioIntervalRef.current) clearInterval(audioIntervalRef.current);
      if (autoSubmitIntervalRef.current) clearInterval(autoSubmitIntervalRef.current);
      if (speechRecognitionRef.current) {
        try {
          speechRecognitionRef.current.stop();
        } catch (e) {}
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, [initMediaStream]);

  // Finalize master session video and complete interview
  const triggerFinishSession = useCallback(async (sessionExpired: boolean) => {
    setSessionStatus('finalizing');
    cancelAutoSubmit();
    if (speechRecognitionRef.current) {
      try {
        speechRecognitionRef.current.stop();
      } catch (e) {}
    }
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

    const masterRecorder = masterRecorderRef.current;
    const finishMaster = async () => {
      const mimeType = getSupportedMimeType();
      const masterBlob = new Blob(masterChunksRef.current, { type: mimeType || 'video/webm' });
      try {
        await onFinishMasterSessionRef.current(masterBlob);
      } catch (err: any) {
        setErrorMessage(err.message || 'Error saving session recording.');
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
  }, [cancelAutoSubmit]);

  const triggerFinishSessionRef = useRef(triggerFinishSession);
  useEffect(() => {
    triggerFinishSessionRef.current = triggerFinishSession;
  }, [triggerFinishSession]);

  // Trigger question transition: stops current question chunk recorder and submits chunk
  const triggerQuestionTransition = useCallback(async () => {
    if (isTransitioningRef.current) return;
    isTransitioningRef.current = true;
    cancelAutoSubmit();

    const qIdToSubmit = currentRecordingQIdRef.current;
    const qRecorder = questionRecorderRef.current;

    const finishChunkAndSubmit = async () => {
      const chunkBlob = new Blob(questionChunksRef.current, { type: 'audio/webm' });
      questionChunksRef.current = [];

      try {
        await onSubmitQuestionAnswerRef.current(chunkBlob, qIdToSubmit);
      } catch (err) {
        console.error(`[AnswerRecorder] Answer submission error for question ${qIdToSubmit}:`, err);
      }

      if (isLastQuestionRef.current) {
        await triggerFinishSessionRef.current(false);
      } else {
        await onAdvanceQuestionRef.current();
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
  }, [cancelAutoSubmit]);

  const triggerQuestionTransitionRef = useRef(triggerQuestionTransition);
  useEffect(() => {
    triggerQuestionTransitionRef.current = triggerQuestionTransition;
  }, [triggerQuestionTransition]);

  // Active session timer
  useEffect(() => {
    if (sessionStatus !== 'recording') return;

    const interval = setInterval(() => {
      // 1. Session total elapsed seconds
      setSessionElapsedSeconds((prev) => {
        const nextSec = prev + 1;
        if (nextSec >= 600) {
          triggerFinishSessionRef.current(true);
        }
        return nextSec;
      });

      // 2. Think Time Countdown
      setThinkTimeRemaining((prev) => {
        if (prev === null) return null;
        if (prev <= 1) return null;
        return prev - 1;
      });

      // 3. Per-question countdown (runs after think time)
      setQuestionRemainingSeconds((prev) => {
        if (thinkTimeRemaining !== null && thinkTimeRemaining > 0) {
          return prev;
        }
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
  }, [sessionStatus, thinkTimeRemaining]);

  // Skip think time and start answering immediately
  const handleSkipThinkTime = () => {
    setThinkTimeRemaining(null);
  };

  // Watch for question changes
  useEffect(() => {
    if (sessionStatus === 'recording' && activeQuestionId && activeQuestionId !== currentRecordingQIdRef.current) {
      currentRecordingQIdRef.current = activeQuestionId;
      const newDur = getDurationForDifficulty(questionDifficulty);
      setQuestionTotalSeconds(newDur);
      setQuestionRemainingSeconds(newDur);
      setThinkTimeRemaining(30);
      isTransitioningRef.current = false;
      cancelAutoSubmit();
      liveTranscriptRef.current = '';
      continuousSilenceMsRef.current = 0;
      setSpokenInsight(null);
      startQuestionAudioRecorder(activeQuestionId);
    }
  }, [activeQuestionId, cancelAutoSubmit, questionDifficulty, questionNumber, sessionStatus, startQuestionAudioRecorder]);

  // Format time utility: MM:SS
  const formatTimer = (seconds: number) => {
    const mins = Math.floor(Math.max(0, seconds) / 60);
    const secs = Math.max(0, seconds) % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Dynamic progress bar percentage
  const progressPercent = Math.max(0, Math.min(100, (questionRemainingSeconds / (questionTotalSeconds || 1)) * 100));
  const progressBarColor =
    questionRemainingSeconds <= 20
      ? '#ef4444'
      : questionRemainingSeconds <= 45
      ? '#f59e0b'
      : '#10b981';

  return (
    <div style={{ marginTop: '0.75rem' }}>
      {/* Clean Candidate Camera Frame */}
      <div style={{
        position: 'relative',
        width: '100%',
        maxWidth: '720px',
        margin: '0 auto',
        borderRadius: '16px',
        overflow: 'hidden',
        backgroundColor: '#020617',
        boxShadow: '0 8px 24px -4px rgba(0, 0, 0, 0.25)',
        border: '1px solid #1e293b',
        aspectRatio: '16/9',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {/* Mirrored Video Stream */}
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
            transform: 'scaleX(-1)',
          }}
        />

        {/* Minimal Non-Distracting Status Indicator (Top-Left) */}
        {sessionStatus === 'recording' && (
          <div style={{
            position: 'absolute',
            top: '0.85rem',
            left: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            padding: '0.35rem 0.75rem',
            borderRadius: '9999px',
            color: '#ffffff',
            fontSize: '0.8rem',
            fontWeight: 700,
            backdropFilter: 'blur(8px)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            zIndex: 10,
          }}>
            <span style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: thinkTimeRemaining !== null && thinkTimeRemaining > 0 ? '#a78bfa' : '#ef4444',
              display: 'inline-block',
              boxShadow: thinkTimeRemaining !== null && thinkTimeRemaining > 0 ? '0 0 6px #a78bfa' : '0 0 6px #ef4444',
            }} />
            {thinkTimeRemaining !== null && thinkTimeRemaining > 0 ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span>💡 Think Time: {thinkTimeRemaining}s</span>
                <button
                  type="button"
                  onClick={handleSkipThinkTime}
                  style={{
                    backgroundColor: '#4f46e5',
                    color: '#ffffff',
                    fontWeight: 700,
                    fontSize: '0.7rem',
                    padding: '0.15rem 0.55rem',
                    borderRadius: '9999px',
                    border: 'none',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  Answer Now ➔
                </button>
              </div>
            ) : (
              <span>● REC Q{questionNumber} &bull; {formatTimer(questionRemainingSeconds)}</span>
            )}
          </div>
        )}

        {/* Alert Badge only on abnormal detections (Top-Right) */}
        {(phoneDetected || faceStatus === 'multiple_faces' || faceStatus === 'no_face') && (
          <div style={{
            position: 'absolute',
            top: '0.85rem',
            right: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            backgroundColor: (phoneDetected || faceStatus === 'multiple_faces') ? 'rgba(220, 38, 38, 0.92)' : 'rgba(217, 119, 6, 0.92)',
            padding: '0.35rem 0.75rem',
            borderRadius: '9999px',
            color: '#ffffff',
            fontSize: '0.78rem',
            fontWeight: 700,
            backdropFilter: 'blur(6px)',
            border: (phoneDetected || faceStatus === 'multiple_faces') ? '1px solid #ef4444' : '1px solid #f59e0b',
            zIndex: 10,
          }}>
            {phoneDetected && <span>🚨 Mobile Phone Detected</span>}
            {!phoneDetected && faceStatus === 'multiple_faces' && <span>🚨 Multiple Faces</span>}
            {!phoneDetected && faceStatus === 'no_face' && <span>⚠️ Face Out of Frame</span>}
          </div>
        )}

        {/* 4-Pillar Adaptive Soft-Landing Countdown Pill (Pillar 4) */}
        {sessionStatus === 'recording' && autoSubmitCountdown !== null && (
          <div
            style={{
              position: 'absolute',
              bottom: '1.25rem',
              left: '50%',
              transform: 'translateX(-50%)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.85rem',
              backgroundColor: 'rgba(15, 23, 42, 0.92)',
              backdropFilter: 'blur(16px)',
              border: '1px solid rgba(245, 158, 11, 0.6)',
              boxShadow: '0 12px 30px -4px rgba(0, 0, 0, 0.6), 0 0 20px rgba(245, 158, 11, 0.3)',
              padding: '0.6rem 1.25rem',
              borderRadius: '9999px',
              color: '#ffffff',
              fontSize: '0.85rem',
              fontWeight: 600,
              zIndex: 20,
              maxWidth: '92%',
              whiteSpace: 'nowrap',
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fef08a' }}>
              <span style={{ fontSize: '1.1rem' }}>⏳</span>
              <span>
                Taking a pause? Auto-submitting in{' '}
                <strong style={{ color: '#fbbf24', fontSize: '1.05rem', fontWeight: 800 }}>
                  {autoSubmitCountdown}s
                </strong>
              </span>
            </span>
            <button
              type="button"
              onClick={cancelAutoSubmit}
              style={{
                backgroundColor: '#3b82f6',
                color: '#ffffff',
                border: 'none',
                borderRadius: '9999px',
                padding: '0.35rem 0.85rem',
                fontSize: '0.78rem',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                transition: 'all 0.15s ease',
                boxShadow: '0 2px 8px rgba(59, 130, 246, 0.4)',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#2563eb')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#3b82f6')}
            >
              <span>➕ Add More</span>
              <span style={{ opacity: 0.8, fontSize: '0.7rem' }}>(or speak)</span>
            </button>
          </div>
        )}

        {/* Finalizing Overlay */}
        {sessionStatus === 'finalizing' && (
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.92)',
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
            <h4 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.35rem' }}>
              Finalizing Interview...
            </h4>
            <p style={{ fontSize: '0.85rem', color: '#94a3b8', maxWidth: '380px', margin: 0 }}>
              Saving continuous recording, processing transcripts, and compiling scorecard.
            </p>
          </div>
        )}

        {/* Permission Error Overlay */}
        {permissionError && (
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            textAlign: 'center',
            color: '#ffffff',
            zIndex: 25,
          }}>
            <div style={{ fontSize: '2.2rem', marginBottom: '0.5rem' }}>📹🚫</div>
            <h4 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              Camera & Microphone Access Required
            </h4>
            <p style={{ fontSize: '0.85rem', color: '#94a3b8', maxWidth: '420px', marginBottom: '1.25rem', lineHeight: 1.4 }}>
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

      {/* Clean Dynamic Countdown Progress Line */}
      {sessionStatus === 'recording' && (
        <div style={{
          maxWidth: '720px',
          margin: '0.45rem auto 0 auto',
          backgroundColor: '#e2e8f0',
          height: '4px',
          borderRadius: '9999px',
          overflow: 'hidden',
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

      {/* Control Bar: Done Answering & Mode Switch */}
      <div style={{
        marginTop: '1rem',
        maxWidth: '720px',
        margin: '1rem auto 0 auto',
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
                : 'Done Answering & Next Question →'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};

