'use client';

import React, { useState, useEffect, useRef } from 'react';

interface PreFlightCheckProps {
  onProceed: () => void;
  candidateName?: string;
  interviewTitle?: string;
}

export const PreFlightCheck: React.FC<PreFlightCheckProps> = ({
  onProceed,
  candidateName = 'Candidate',
  interviewTitle = 'Technical Screen & Competency Assessment',
}) => {
  const [hasCamera, setHasCamera] = useState<boolean | null>(null);
  const [hasMic, setHasMic] = useState<boolean | null>(null);
  const [micVolume, setMicVolume] = useState<number>(0);
  const [isSpeakerTesting, setIsSpeakerTesting] = useState(false);
  const [resolutionText, setResolutionText] = useState<string>('Detecting...');
  const [permissionError, setPermissionError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function setupDevices() {
      try {
        setPermissionError(null);
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });

        if (!isMounted) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.onloadedmetadata = () => {
            if (videoRef.current) {
              const w = videoRef.current.videoWidth;
              const h = videoRef.current.videoHeight;
              setResolutionText(w && h ? `${w}x${h} HD` : '720p HD');
            }
          };
        }

        setHasCamera(true);
        setHasMic(true);

        // Web Audio API for Real-Time Microphone Volume Level Meter
        const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
        if (AudioContextClass) {
          const audioContext = new AudioContextClass();
          audioContextRef.current = audioContext;

          if (audioContext.state === 'suspended') {
            await audioContext.resume();
          }

          const analyser = audioContext.createAnalyser();
          analyser.fftSize = 256;
          analyser.smoothingTimeConstant = 0.6;

          const source = audioContext.createMediaStreamSource(stream);
          source.connect(analyser);

          const dataArray = new Uint8Array(analyser.frequencyBinCount);

          const updateVolume = () => {
            if (!isMounted) return;
            analyser.getByteFrequencyData(dataArray);
            const sum = dataArray.reduce((acc, val) => acc + val, 0);
            const average = sum / dataArray.length;
            const normalized = Math.min(100, Math.round((average / 110) * 100));
            setMicVolume(normalized);
            animationFrameRef.current = requestAnimationFrame(updateVolume);
          };

          updateVolume();
        }
      } catch (err: any) {
        console.error('Pre-flight device setup error:', err);
        if (isMounted) {
          setHasCamera(false);
          setHasMic(false);
          setPermissionError(
            err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError'
              ? 'Camera or Microphone access was denied in browser permissions. Please allow access to proceed.'
              : 'Could not connect to camera or microphone. Please check your hardware connections.'
          );
        }
      }
    }

    setupDevices();

    return () => {
      isMounted = false;
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, []);

  const handleTestSpeakers = () => {
    setIsSpeakerTesting(true);
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtx) {
        const ctx = new AudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
        osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15); // A5
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.45);
      }
    } catch (e) {
      console.warn('Speaker audio synth test error:', e);
    }
    setTimeout(() => {
      setIsSpeakerTesting(false);
    }, 800);
  };

  const handleStart = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
    }
    onProceed();
  };

  const isReady = Boolean(hasCamera && hasMic);

  return (
    <div
      style={{
        maxWidth: '960px',
        margin: '2rem auto',
        padding: '0 1rem 3rem 1rem',
        fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: '16px',
          boxShadow: '0 4px 20px -2px rgba(0, 0, 0, 0.05)',
          padding: '2.25rem',
        }}
      >
        {/* Header */}
        <div
          style={{
            borderBottom: '1px solid #f1f5f9',
            paddingBottom: '1.25rem',
            marginBottom: '1.75rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '1.4rem' }}>🛡️</span>
              <h1 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', margin: 0, letterSpacing: '-0.02em' }}>
                Pre-Flight System & Device Readiness Check
              </h1>
            </div>
            <p style={{ color: '#64748b', fontSize: '0.9rem', margin: 0 }}>
              {interviewTitle} &bull; Candidate:{' '}
              <strong style={{ color: '#2563eb' }}>{candidateName}</strong>
            </p>
          </div>

          <div
            style={{
              padding: '0.35rem 0.85rem',
              fontSize: '0.75rem',
              fontWeight: 700,
              backgroundColor: '#eff6ff',
              color: '#2563eb',
              border: '1px solid #dbeafe',
              borderRadius: '9999px',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
            }}
          >
            AI Interview Room
          </div>
        </div>

        {permissionError && (
          <div
            style={{
              marginBottom: '1.5rem',
              padding: '1rem 1.25rem',
              backgroundColor: '#fee2e2',
              border: '1px solid #fca5a5',
              borderRadius: '12px',
              color: '#991b1b',
              fontSize: '0.875rem',
              lineHeight: 1.5,
              display: 'flex',
              gap: '0.75rem',
              alignItems: 'center',
            }}
          >
            <span style={{ fontSize: '1.3rem' }}>🚫</span>
            <div>
              <strong>Permission Required:</strong> {permissionError}
            </div>
          </div>
        )}

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '1.75rem',
          }}
        >
          {/* Left: Video Preview */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div
              style={{
                position: 'relative',
                width: '100%',
                aspectRatio: '16 / 9',
                backgroundColor: '#0f172a',
                borderRadius: '12px',
                overflow: 'hidden',
                border: '1px solid #cbd5e1',
                boxShadow: '0 4px 10px rgba(0, 0, 0, 0.08)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  transform: 'scaleX(-1)', // Mirror view for natural feel
                }}
              />

              {!hasCamera && hasCamera !== null && (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    backgroundColor: 'rgba(255, 255, 255, 0.96)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '1.5rem',
                    textAlign: 'center',
                    color: '#dc2626',
                  }}
                >
                  <span style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📷❌</span>
                  <p style={{ fontWeight: 700, fontSize: '0.95rem', margin: '0 0 0.35rem 0' }}>
                    Camera Access Not Available
                  </p>
                  <p style={{ fontSize: '0.8rem', color: '#64748b', margin: 0 }}>
                    Please grant camera permissions in your browser address bar.
                  </p>
                </div>
              )}

              {hasCamera && (
                <div
                  style={{
                    position: 'absolute',
                    bottom: '12px',
                    left: '12px',
                    backgroundColor: 'rgba(15, 23, 42, 0.8)',
                    backdropFilter: 'blur(8px)',
                    padding: '0.35rem 0.65rem',
                    borderRadius: '8px',
                    fontSize: '0.75rem',
                    fontFamily: 'monospace',
                    color: '#34d399',
                    border: '1px solid rgba(52, 211, 153, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.45rem',
                  }}
                >
                  <span
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: '#34d399',
                      boxShadow: '0 0 8px #34d399',
                    }}
                  />
                  Webcam Active ({resolutionText})
                </div>
              )}
            </div>

            <div
              style={{
                fontSize: '0.8rem',
                color: '#64748b',
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <span>💡</span> Position yourself in good lighting with your face centered.
            </div>
          </div>

          {/* Right: Audio & Checks List */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: '1.25rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {/* Mic Status & Live Bar */}
              <div
                style={{
                  backgroundColor: '#f8fafc',
                  padding: '1.15rem',
                  borderRadius: '12px',
                  border: '1px solid #e2e8f0',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '0.65rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <span style={{ fontSize: '1rem' }}>🎙️</span>
                    <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a' }}>Microphone Input</span>
                  </div>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.2rem 0.6rem',
                      borderRadius: '6px',
                      fontWeight: 700,
                      backgroundColor: hasMic ? '#dcfce7' : '#fee2e2',
                      color: hasMic ? '#15803d' : '#b91c1c',
                    }}
                  >
                    {hasMic ? 'Connected' : 'Unavailable'}
                  </span>
                </div>

                <div
                  style={{
                    width: '100%',
                    backgroundColor: '#e2e8f0',
                    height: '10px',
                    borderRadius: '9999px',
                    overflow: 'hidden',
                    border: '1px solid #cbd5e1',
                  }}
                >
                  <div
                    style={{
                      background: 'linear-gradient(90deg, #10b981 0%, #06b6d4 60%, #3b82f6 100%)',
                      height: '100%',
                      width: `${micVolume}%`,
                      transition: 'width 0.08s ease-out',
                      borderRadius: '9999px',
                      boxShadow: micVolume > 10 ? '0 0 10px rgba(16, 185, 129, 0.5)' : 'none',
                    }}
                  />
                </div>
                <p style={{ fontSize: '0.75rem', color: '#64748b', margin: '0.5rem 0 0 0' }}>
                  Speak out loud to verify your microphone level (ideal active range: 40% – 85%).
                </p>
              </div>

              {/* Speaker Test */}
              <div
                style={{
                  backgroundColor: '#f8fafc',
                  padding: '1.15rem',
                  borderRadius: '12px',
                  border: '1px solid #e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '1rem',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.2rem' }}>
                    <span style={{ fontSize: '1rem' }}>🔊</span>
                    <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                      Audio Output (Speakers)
                    </h4>
                  </div>
                  <p style={{ fontSize: '0.75rem', color: '#64748b', margin: 0 }}>
                    Ensure you can hear the AI interviewer questions clearly.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleTestSpeakers}
                  disabled={isSpeakerTesting}
                  style={{
                    padding: '0.5rem 0.95rem',
                    backgroundColor: isSpeakerTesting ? '#e2e8f0' : '#ffffff',
                    color: '#0f172a',
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    cursor: isSpeakerTesting ? 'default' : 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                  }}
                >
                  {isSpeakerTesting ? '🎵 Playing Sound...' : 'Play Test Chime'}
                </button>
              </div>

              {/* Security & Proctoring Notice */}
              <div
                style={{
                  backgroundColor: '#eff6ff',
                  border: '1px solid #bfdbfe',
                  padding: '0.85rem 1rem',
                  borderRadius: '10px',
                  fontSize: '0.78rem',
                  color: '#1e40af',
                  lineHeight: 1.45,
                }}
              >
                ℹ️ <strong>Proctoring Notice:</strong> Please ensure quiet surroundings and stay in full-screen window mode during evaluation. Tab switches and multiple faces are automatically flagged.
              </div>
            </div>

            {/* Launch Button */}
            <button
              type="button"
              onClick={handleStart}
              disabled={!isReady}
              style={{
                width: '100%',
                padding: '0.95rem 1.5rem',
                borderRadius: '12px',
                fontWeight: 800,
                fontSize: '0.95rem',
                letterSpacing: '0.02em',
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                backgroundColor: isReady ? '#2563eb' : '#f1f5f9',
                color: isReady ? '#ffffff' : '#94a3b8',
                border: isReady ? '1px solid #2563eb' : '1px solid #e2e8f0',
                cursor: isReady ? 'pointer' : 'not-allowed',
                boxShadow: isReady ? '0 10px 25px -5px rgba(37, 99, 235, 0.35)' : 'none',
              }}
            >
              {isReady ? 'I Am Ready — Start Interview ➔' : 'Please Allow Camera & Mic Access to Proceed'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

