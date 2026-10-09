'use client';
import React, { useEffect, useRef, useState } from 'react';
import { Card } from '../../components/Card';
import { getDifficultyBadgeColor } from '../../lib/utils';
import { Question } from '../../lib/types';
import { api } from '../../lib/api';
import { LiveEqualizer } from './LiveEqualizer';

interface QuestionCardProps {
  question: Question;
  questionNumber: number | string;
  totalQuestions: number;
}

export const QuestionCard: React.FC<QuestionCardProps> = ({
  question,
  questionNumber,
  totalQuestions,
}) => {
  const diffColors = getDifficultyBadgeColor(question.difficulty);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioError, setAudioError] = useState(false);
  const [videoError, setVideoError] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Compute URLs
  const audioUrl = question.audio_url
    ? (question.audio_url.startsWith('http')
        ? question.audio_url
        : `${apiBase}${question.audio_url.startsWith('/') ? '' : '/'}${question.audio_url}`)
    : (question.session_id && question.id
        ? api.getQuestionAudioUrl(question.session_id, question.id)
        : null);

  const avatarVideoUrl = question.avatar_video_url
    ? (question.avatar_video_url.startsWith('http')
        ? question.avatar_video_url
        : `${apiBase}${question.avatar_video_url.startsWith('/') ? '' : '/'}${question.avatar_video_url}`)
    : (question.session_id && question.id && !question.is_followup && question.interviewer_photo_url
        ? api.getQuestionAvatarVideoUrl(question.session_id, question.id)
        : null);

  const interviewerPhotoUrl = question.interviewer_photo_url
    ? (question.interviewer_photo_url.startsWith('http')
        ? question.interviewer_photo_url
        : `${apiBase}${question.interviewer_photo_url.startsWith('/') ? '' : '/'}${question.interviewer_photo_url}`)
    : (question.session_id
        ? api.getInterviewerPhotoUrl(question.session_id)
        : null);

  // Avatar (video or photo fallback) is only shown for main questions, not counter questions
  const hasVideoAvatar = Boolean(avatarVideoUrl && !videoError && !question.is_followup);
  const hasPhotoAvatar = Boolean(interviewerPhotoUrl && !question.is_followup && (videoError || !avatarVideoUrl));

  // Handle Playback Speed Change
  const handleSpeedChange = (speed: number) => {
    setPlaybackSpeed(speed);
    if (audioRef.current) audioRef.current.playbackRate = speed;
    if (videoRef.current) videoRef.current.playbackRate = speed;
  };

  // Toggle Play/Pause
  const togglePlay = () => {
    if (hasVideoAvatar && videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
        setIsPlaying(false);
      } else {
        videoRef.current.play()
          .then(() => setIsPlaying(true))
          .catch(() => setVideoError(true));
      }
    } else if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        audioRef.current.play()
          .then(() => setIsPlaying(true))
          .catch(() => setAudioError(true));
      }
    }
  };

  // Auto-play when question changes
  useEffect(() => {
    setIsPlaying(false);
    setAudioError(false);
    setVideoError(false);

    if (hasVideoAvatar && videoRef.current) {
      videoRef.current.currentTime = 0;
      videoRef.current.playbackRate = playbackSpeed;
      videoRef.current.play()
        .then(() => setIsPlaying(true))
        .catch((err) => {
          console.log('[AVATAR] Autoplay deferred until user gesture:', err.message);
          setIsPlaying(false);
        });
    } else if (audioRef.current && audioUrl) {
      audioRef.current.currentTime = 0;
      audioRef.current.playbackRate = playbackSpeed;
      audioRef.current.play()
        .then(() => setIsPlaying(true))
        .catch((err) => {
          console.log('[TTS] Autoplay deferred until user gesture:', err.message);
          setIsPlaying(false);
        });
    }
  }, [question.id, audioUrl, avatarVideoUrl]);

  return (
    <Card style={{
      marginBottom: '1.5rem',
      borderLeft: question.is_followup ? '4px solid #8b5cf6' : '4px solid #2563eb',
      backgroundColor: question.is_followup ? '#faf5ff' : '#ffffff',
      transition: 'all 0.3s ease',
    }}>
      {/* Underlying Audio Player (used when video is absent or in amplitude animation mode) */}
      {audioUrl && !hasVideoAvatar && (
        <audio
          key={question.id}
          ref={audioRef}
          src={audioUrl}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
          onError={() => {
            console.warn('[TTS] Audio playback error for question:', question.id);
            setIsPlaying(false);
            setAudioError(true);
          }}
          preload="auto"
        />
      )}

      {/* Header Tags */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '1rem',
        flexWrap: 'wrap',
        gap: '0.5rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <span style={{
            fontSize: '0.85rem',
            fontWeight: 700,
            color: question.is_followup ? '#7c3aed' : '#2563eb',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}>
            {question.is_followup ? 'Follow-Up Question' : `Question ${questionNumber} of ${totalQuestions}`}
          </span>

          {question.is_followup && (
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.25rem',
              fontSize: '0.75rem',
              fontWeight: 800,
              backgroundColor: '#ede9fe',
              color: '#6d28d9',
              padding: '0.2rem 0.65rem',
              borderRadius: '9999px',
              border: '1px solid #ddd6fe',
            }}>
              <span>⚡</span> DYNAMIC FOLLOW-UP
            </span>
          )}

          <span style={{
            fontSize: '0.75rem',
            fontWeight: 600,
            backgroundColor: '#f1f5f9',
            color: '#475569',
            padding: '0.2rem 0.6rem',
            borderRadius: '6px',
          }}>
            {question.skill_tag}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{
            fontSize: '0.75rem',
            fontWeight: 700,
            backgroundColor: diffColors.bg,
            color: diffColors.text,
            padding: '0.2rem 0.6rem',
            borderRadius: '9999px',
            textTransform: 'uppercase',
          }}>
            {question.difficulty}
          </span>

          {question.mock && (
            <span style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              backgroundColor: '#fef3c7',
              color: '#b45309',
              padding: '0.15rem 0.5rem',
              borderRadius: '4px',
              border: '1px solid #fde68a',
            }}>
              MOCK
            </span>
          )}
        </div>
      </div>

      {/* Main Content Layout: Question Text + Optional Avatar Display */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: (hasVideoAvatar || hasPhotoAvatar) ? '1fr 220px' : '1fr',
        gap: '1.25rem',
        alignItems: 'start',
      }}>
        <div>
          <p style={{
            fontSize: '1.2rem',
            fontWeight: 600,
            color: '#1e293b',
            lineHeight: 1.6,
            margin: '0 0 1rem 0',
          }}>
            {question.text}
          </p>

          {/* Controls Bar */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid #f1f5f9',
            flexWrap: 'wrap',
          }}>
            <button
              type="button"
              onClick={togglePlay}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.4rem 0.85rem',
                fontSize: '0.8rem',
                fontWeight: 600,
                backgroundColor: isPlaying ? '#dbeafe' : '#f8fafc',
                color: isPlaying ? '#1d4ed8' : '#475569',
                border: `1px solid ${isPlaying ? '#93c5fd' : '#cbd5e1'}`,
                borderRadius: '6px',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              <span>{isPlaying ? '⏸️ Pause Voice' : '🔊 Replay Voice'}</span>
            </button>

            {/* Playback speed toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', backgroundColor: '#f1f5f9', borderRadius: '6px', padding: '0.15rem' }}>
              {[0.85, 1.0, 1.15].map((speed) => (
                <button
                  key={speed}
                  type="button"
                  onClick={() => handleSpeedChange(speed)}
                  style={{
                    border: 'none',
                    backgroundColor: playbackSpeed === speed ? '#ffffff' : 'transparent',
                    color: playbackSpeed === speed ? '#2563eb' : '#64748b',
                    fontSize: '0.72rem',
                    fontWeight: playbackSpeed === speed ? 700 : 500,
                    borderRadius: '4px',
                    padding: '0.2rem 0.45rem',
                    cursor: 'pointer',
                    boxShadow: playbackSpeed === speed ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
                  }}
                >
                  {speed}x
                </button>
              ))}
            </div>

            {isPlaying && (
              <LiveEqualizer isActive={true} mode="speaking" />
            )}

          </div>
        </div>

        {/* Avatar Presentation Column */}
        {(hasVideoAvatar || hasPhotoAvatar) && (
          <div
            onClick={togglePlay}
            title={isPlaying ? "Click to Pause Voice" : "Click to Play Interviewer Video"}
            style={{
              position: 'relative',
              width: '100%',
              maxWidth: '220px',
              borderRadius: '12px',
              overflow: 'hidden',
              backgroundColor: '#0f172a',
              border: isPlaying ? '2px solid #3b82f6' : '1px solid #cbd5e1',
              boxShadow: isPlaying ? '0 0 16px rgba(59, 130, 246, 0.35)' : '0 2px 4px rgba(0,0,0,0.05)',
              transition: 'all 0.3s ease',
              cursor: 'pointer',
              userSelect: 'none',
            }}
          >
            {/* Mode 1: Pre-rendered Wav2Lip MP4 Video for Bank Questions */}
            {hasVideoAvatar && avatarVideoUrl && (
              <video
                ref={videoRef}
                src={avatarVideoUrl}
                playsInline
                preload="auto"
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
                onError={() => {
                  console.warn('[AVATAR] Video load error, falling back to audio/photo mode');
                  setVideoError(true);
                }}
                style={{
                  width: '100%',
                  aspectRatio: '1/1',
                  objectFit: 'cover',
                  display: 'block',
                }}
              />
            )}

            {/* Mode 2: Real-time Live Photo with Speaking Wave for Follow-Ups or Audio Fallback */}
            {(!hasVideoAvatar && hasPhotoAvatar && interviewerPhotoUrl) && (
              <div style={{ position: 'relative', width: '100%', aspectRatio: '1/1', overflow: 'hidden' }}>
                <img
                  src={interviewerPhotoUrl}
                  alt="Interviewer Avatar"
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    display: 'block',
                    transform: isPlaying ? 'scale(1.03)' : 'scale(1.0)',
                    transition: 'transform 0.25s ease-in-out',
                  }}
                />
              </div>
            )}

            {/* Centered Play Button Overlay (when paused / not playing) */}
            {!isPlaying && (
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: 'rgba(15, 23, 42, 0.4)',
                backdropFilter: 'blur(2px)',
                transition: 'all 0.2s ease',
              }}>
                <div style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '50%',
                  backgroundColor: 'rgba(255, 255, 255, 0.95)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                  color: '#1d4ed8',
                  fontSize: '1.2rem',
                  paddingLeft: '3px',
                }}>
                  ▶
                </div>
                <span style={{
                  marginTop: '0.4rem',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  color: '#ffffff',
                  textShadow: '0 1px 3px rgba(0,0,0,0.8)',
                  backgroundColor: 'rgba(0,0,0,0.5)',
                  padding: '0.15rem 0.5rem',
                  borderRadius: '9999px',
                }}>
                  Click to Play
                </span>
              </div>
            )}

            {/* Overlay Status Badge */}
            <div style={{
              position: 'absolute',
              bottom: '6px',
              left: '6px',
              right: '6px',
              backgroundColor: 'rgba(15, 23, 42, 0.8)',
              backdropFilter: 'blur(4px)',
              padding: '0.2rem 0.45rem',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <span style={{ fontSize: '0.65rem', fontWeight: 700, color: '#f8fafc', letterSpacing: '0.02em' }}>
                {isPlaying ? 'Speaking...' : (hasVideoAvatar ? 'AI Avatar' : 'Live Avatar')}
              </span>
              <span style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: isPlaying ? '#22c55e' : '#94a3b8',
                boxShadow: isPlaying ? '0 0 8px #22c55e' : 'none',
              }} />
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};
