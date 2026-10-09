'use client';

import React from 'react';

interface LiveEqualizerProps {
  isActive: boolean;
  mode: 'listening' | 'speaking' | 'thinking';
  customLabel?: string;
}

export const LiveEqualizer: React.FC<LiveEqualizerProps> = ({
  isActive,
  mode,
  customLabel,
}) => {
  const getColors = () => {
    if (mode === 'speaking') {
      return {
        bar: '#818cf8',
        glow: 'rgba(99, 102, 241, 0.4)',
        border: 'rgba(99, 102, 241, 0.3)',
        bg: 'rgba(30, 27, 75, 0.85)',
        text: '#c7d2fe',
        dot: '#6366f1',
      };
    }
    if (mode === 'listening') {
      return {
        bar: '#34d399',
        glow: 'rgba(16, 185, 129, 0.4)',
        border: 'rgba(16, 185, 129, 0.3)',
        bg: 'rgba(6, 78, 59, 0.85)',
        text: '#a7f3d0',
        dot: '#10b981',
      };
    }
    return {
      bar: '#fbbf24',
      glow: 'rgba(245, 158, 11, 0.4)',
      border: 'rgba(245, 158, 11, 0.3)',
      bg: 'rgba(69, 26, 3, 0.85)',
      text: '#fde68a',
      dot: '#f59e0b',
    };
  };

  const getLabel = () => {
    if (customLabel) return customLabel;
    if (mode === 'speaking') return 'AI Interviewer Speaking...';
    if (mode === 'listening') return 'Listening to Candidate Voice...';
    return 'AI Evaluating Response & Thinking...';
  };

  const colors = getColors();

  // Distinct heights for natural audio spectrum wave pattern
  const barHeights = [35, 75, 100, 60, 90, 45, 80, 50];

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.65rem',
        backgroundColor: colors.bg,
        border: `1px solid ${colors.border}`,
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        padding: '0.45rem 0.95rem',
        borderRadius: '9999px',
        boxShadow: isActive ? `0 4px 14px ${colors.glow}` : '0 2px 6px rgba(0,0,0,0.2)',
        transition: 'all 0.25s ease',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '3px',
          height: '18px',
        }}
      >
        {barHeights.map((h, i) => (
          <span
            key={i}
            style={{
              display: 'inline-block',
              width: '3px',
              borderRadius: '9999px',
              backgroundColor: colors.bar,
              height: isActive ? `${h}%` : '4px',
              opacity: isActive ? 1 : 0.4,
              transition: 'height 0.15s ease, opacity 0.2s ease',
              animation: isActive ? `eqPulse 0.9s ease-in-out infinite alternate` : 'none',
              animationDelay: `${(i * 120) % 600}ms`,
            }}
          />
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: colors.dot,
            boxShadow: isActive ? `0 0 6px ${colors.dot}` : 'none',
          }}
        />
        <span
          style={{
            fontSize: '0.78rem',
            fontWeight: 700,
            color: colors.text,
            letterSpacing: '0.02em',
          }}
        >
          {getLabel()}
        </span>
      </div>

      <style jsx>{`
        @keyframes eqPulse {
          0% {
            transform: scaleY(0.4);
          }
          50% {
            transform: scaleY(1);
          }
          100% {
            transform: scaleY(0.6);
          }
        }
      `}</style>
    </div>
  );
};
