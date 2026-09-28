'use client';

import { useEffect, useRef } from 'react';
import { api } from '@/lib/api';

interface ProctoringWarning {
  title: string;
  message: string;
  severity: 'low' | 'medium' | 'high';
}

interface ProctoringMonitorProps {
  sessionId: string;
  activeQuestionId?: string | null;
  isActive: boolean;
  onWarning?: (warning: ProctoringWarning) => void;
}

export function ProctoringMonitor({
  sessionId,
  activeQuestionId,
  isActive,
  onWarning,
}: ProctoringMonitorProps) {
  const lastTabSwitchRef = useRef<number>(0);
  const lastBlurRef = useRef<number>(0);
  const multiScreenCheckedRef = useRef<boolean>(false);

  useEffect(() => {
    if (!isActive || !sessionId) return;

    let wasHidden = false;
    let hiddenTimestamp = 0;

    // Helper to capture off-screen camera snapshot for proof
    const captureCameraSnapshot = (): string | null => {
      try {
        const video = document.querySelector('video');
        if (!video || video.readyState < 2) return null;
        const canvas = document.createElement('canvas');
        canvas.width = 640;
        canvas.height = 360;
        const ctx = canvas.getContext('2d');
        if (!ctx) return null;
        ctx.drawImage(video, 0, 0, 640, 360);
        return canvas.toDataURL('image/jpeg', 0.8);
      } catch {
        return null;
      }
    };

    // 1. Tab Switch Detection (visibilitychange)
    const handleVisibilityChange = async () => {
      if (document.hidden) {
        wasHidden = true;
        hiddenTimestamp = Date.now();
        // Log telemetry event immediately with instant proof snapshot
        const now = Date.now();
        if (now - lastTabSwitchRef.current > 1000) {
          lastTabSwitchRef.current = now;
          const snapshot = captureCameraSnapshot();
          try {
            await api.logProctoringEvent(sessionId, {
              event_type: 'tab_switch',
              question_id: activeQuestionId,
              details: 'Candidate navigated away from interview tab (visibilitychange: hidden)',
              screenshot_base64: snapshot,
            });
          } catch (err) {
            console.warn('[Proctoring] Tab switch telemetry failed:', err);
          }
        }
      } else if (wasHidden) {
        // User just returned to the interview tab! Show the warning on screen now!
        wasHidden = false;
        const awaySeconds = hiddenTimestamp > 0 ? Math.round((Date.now() - hiddenTimestamp) / 1000) : 1;
        onWarning?.({
          title: '🚨 Malpractice Warning: Tab Switch Detected!',
          message: `You navigated away from the interview screen (away for ~${awaySeconds}s). Tab switches are flagged in your recruiter audit report.`,
          severity: 'high',
        });
      }
    };

    let wasBlurred = false;
    // 2. Window Focus Loss & Return Detection (blur & focus)
    const handleWindowBlur = async () => {
      wasBlurred = true;
      const now = Date.now();
      if (now - lastBlurRef.current > 1000) {
        lastBlurRef.current = now;
        const snapshot = captureCameraSnapshot();
        try {
          await api.logProctoringEvent(sessionId, {
            event_type: 'focus_loss',
            question_id: activeQuestionId,
            details: 'Candidate window lost focus (window blur event)',
            screenshot_base64: snapshot,
          });
        } catch (err) {
          console.warn('[Proctoring] Focus loss telemetry failed:', err);
        }
      }
    };

    const handleWindowFocus = () => {
      if (wasBlurred && !document.hidden) {
        wasBlurred = false;
        onWarning?.({
          title: '⚠️ Malpractice Warning: Window Focus Lost!',
          message: 'The interview window lost focus. Please remain focused on the interview test.',
          severity: 'medium',
        });
      }
    };

    // 3. Multi-Monitor / Extended Display Check
    const checkMultiScreen = async () => {
      if (multiScreenCheckedRef.current) return;
      
      let isMultiScreen = false;
      try {
        // Modern Screen Details API (if available)
        if ('isExtended' in window.screen && (window.screen as any).isExtended) {
          isMultiScreen = true;
        } else if (window.screen.availWidth > window.screen.width * 1.5) {
          // Fallback heuristic for virtual spanning displays
          isMultiScreen = true;
        }
      } catch (e) {
        // Ignore permission or browser compatibility errors
      }

      if (isMultiScreen) {
        multiScreenCheckedRef.current = true;
        try {
          await api.logProctoringEvent(sessionId, {
            event_type: 'multi_screen_detected',
            question_id: activeQuestionId,
            details: 'Multiple monitors or extended display detected',
          });
        } catch (err) {
          console.warn('[Proctoring] Multi-screen telemetry failed:', err);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleWindowBlur);
    window.addEventListener('focus', handleWindowFocus);
    checkMultiScreen();

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleWindowBlur);
      window.removeEventListener('focus', handleWindowFocus);
    };
  }, [sessionId, activeQuestionId, isActive]);

  // Telemetry runs completely in the background
  return null;
}
