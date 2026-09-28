'use client';
import React, { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Navbar } from '../../components/Navbar';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { Modal } from '../../components/Modal';
import { api } from '../../lib/api';
import { FullReportResponse } from '../../lib/types';
import { formatScoreBadge, formatRecommendationBadge, formatDate, getDifficultyBadgeColor } from '../../lib/utils';

function ReportContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session_id');

  const [reportData, setReportData] = useState<FullReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedProofScreenshot, setSelectedProofScreenshot] = useState<{
    url: string;
    title: string;
    timestamp: string;
  } | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setIsLoading(false);
      return;
    }
    const fetchReport = async () => {
      try {
        setIsLoading(true);
        setErrorMessage(null);
        const data = await api.getReport(sessionId);
        setReportData(data);
      } catch (err: any) {
        setErrorMessage(err.message || 'Failed to load evaluation report.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchReport();
  }, [sessionId]);

  if (!sessionId) {
    return (
      <div style={{ maxWidth: '600px', margin: '4rem auto', textAlign: 'center' }}>
        <Card>
          <h2>No Session ID Provided</h2>
          <p style={{ color: '#64748b', marginBottom: '1.5rem' }}>
            Please select a candidate from the Recruiter Dashboard to view their evaluation report.
          </p>
          <Link href="/dashboard">
            <Button variant="primary">Go to Recruiter Dashboard →</Button>
          </Link>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div style={{ maxWidth: '700px', margin: '4rem auto', textAlign: 'center' }}>
        <Card>
          <p style={{ color: '#64748b' }}>Loading candidate evaluation report...</p>
        </Card>
      </div>
    );
  }

  if (errorMessage || !reportData || !reportData.report) {
    return (
      <div style={{ maxWidth: '600px', margin: '4rem auto', textAlign: 'center' }}>
        <Card>
          <h2 style={{ color: '#ef4444' }}>Report Not Found</h2>
          <p style={{ color: '#64748b', marginBottom: '1.5rem' }}>
            {errorMessage || 'This interview may still be in progress or has not been finalized yet.'}
          </p>
          <Link href="/dashboard">
            <Button variant="secondary">Back to Dashboard</Button>
          </Link>
        </Card>
      </div>
    );
  }

  const {
    report,
    candidate_name,
    candidate_email,
    overall_score,
    integrity_score,
    integrity_flags = [],
    proctoring_events = [],
    session_video_url,
    completed_at,
    transcript,
  } = reportData;
  const scoreBadge = formatScoreBadge(overall_score);
  const recBadge = formatRecommendationBadge(report.recommendation);

  const formatProctoringSummary = (flags: string[]) => {
    if (!flags || flags.length === 0) {
      return { label: 'Clean (0 Flags)', bg: '#dcfce7', text: '#15803d', sublabel: 'No Anomalies' };
    }
    if (flags.length <= 2) {
      return { label: `${flags.length} Flag${flags.length > 1 ? 's' : ''}`, bg: '#fef3c7', text: '#b45309', sublabel: 'Minor Anomalies' };
    }
    return { label: `${flags.length} Flags`, bg: '#fee2e2', text: '#b91c1c', sublabel: 'Review Required' };
  };
  const proctoringSummary = formatProctoringSummary(integrity_flags);

  return (
    <div style={{ maxWidth: '950px', margin: '2rem auto', padding: '0 1rem 4rem 1rem' }}>
      {/* Header Bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1.5rem',
        flexWrap: 'wrap',
        gap: '1rem',
      }}>
        <Link href="/dashboard" style={{ textDecoration: 'none', color: '#64748b', fontSize: '0.9rem', fontWeight: 600 }}>
          ← Back to Dashboard
        </Link>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {report.mock && (
            <span style={{
              backgroundColor: '#fef3c7',
              color: '#b45309',
              border: '1px solid #fde68a',
              padding: '0.2rem 0.6rem',
              borderRadius: '6px',
              fontSize: '0.75rem',
              fontWeight: 700,
            }}>
              ⚠️ MOCK EVALUATION
            </span>
          )}
          <Button variant="secondary" onClick={() => window.print()} style={{ fontSize: '0.85rem' }}>
            🖨️ Print / Export PDF
          </Button>
        </div>
      </div>

      {/* Candidate Overview Card */}
      <Card style={{ marginBottom: '1.5rem', padding: '1.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Candidate Evaluation Report
            </div>
            <h1 style={{ fontSize: '1.875rem', fontWeight: 800, color: '#0f172a', margin: '0.25rem 0 0.5rem 0' }}>
              {candidate_name}
            </h1>
            <div style={{ fontSize: '0.9rem', color: '#475569', display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
              <span>✉️ {candidate_email}</span>
              <span>📅 Completed: {formatDate(completed_at)}</span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Technical Score Pill */}
            <div style={{
              textAlign: 'center',
              padding: '0.75rem 1.1rem',
              borderRadius: '12px',
              backgroundColor: scoreBadge.bg,
              color: scoreBadge.text,
            }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase' }}>Technical Score</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>{scoreBadge.label}</div>
            </div>

            {/* Proctoring Summary Pill */}
            <div style={{
              textAlign: 'center',
              padding: '0.75rem 1.1rem',
              borderRadius: '12px',
              backgroundColor: proctoringSummary.bg,
              color: proctoringSummary.text,
            }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase' }}>🛡️ Proctoring Status</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800 }}>{proctoringSummary.label}</div>
            </div>

            {/* Recommendation Pill */}
            <div style={{
              textAlign: 'center',
              padding: '0.75rem 1.1rem',
              borderRadius: '12px',
              backgroundColor: recBadge.bg,
              color: recBadge.text,
            }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', opacity: 0.9 }}>Recommendation</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800 }}>{recBadge.label}</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Proctoring Anomaly Notice Banner (if any flags) */}
      {integrity_flags && integrity_flags.length > 0 && (
        <Card style={{
          marginBottom: '1.5rem',
          padding: '1.25rem 1.5rem',
          backgroundColor: '#fffbeb',
          borderLeft: '5px solid #f59e0b',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '1.2rem' }}>⚠️</span>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#92400e' }}>
              Proctoring Telemetry Flags ({integrity_flags.length})
            </h3>
          </div>
          <ul style={{ margin: 0, paddingLeft: '1.25rem', color: '#78350f', fontSize: '0.9rem', lineHeight: 1.5 }}>
            {integrity_flags.map((flag, idx) => (
              <li key={idx} style={{ marginBottom: '0.25rem' }}>{flag}</li>
            ))}
          </ul>
        </Card>
      )}

      {/* Executive Summary Card */}
      <Card style={{ marginBottom: '1.5rem', padding: '1.75rem' }}>
        <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0f172a', margin: '0 0 0.75rem 0' }}>
          Executive AI Summary
        </h2>
        <p style={{ color: '#334155', fontSize: '1rem', lineHeight: 1.6, margin: 0 }}>
          {report.summary_text}
        </p>
      </Card>

      {/* Strengths & Weaknesses Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Strengths */}
        <Card style={{ borderTop: '4px solid #10b981', padding: '1.5rem' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#0f172a', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>💪</span> Key Strengths
          </h3>
          <ul style={{ margin: 0, paddingLeft: '1.25rem', color: '#334155', fontSize: '0.925rem', lineHeight: 1.6 }}>
            {report.strengths.map((str, idx) => (
              <li key={idx} style={{ marginBottom: '0.5rem' }}>{str}</li>
            ))}
          </ul>
        </Card>

        {/* Weaknesses */}
        <Card style={{ borderTop: '4px solid #f59e0b', padding: '1.5rem' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#0f172a', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>🔍</span> Areas for Improvement
          </h3>
          <ul style={{ margin: 0, paddingLeft: '1.25rem', color: '#334155', fontSize: '0.925rem', lineHeight: 1.6 }}>
            {report.weaknesses.map((wk, idx) => (
              <li key={idx} style={{ marginBottom: '0.5rem' }}>{wk}</li>
            ))}
          </ul>
        </Card>
      </div>

      {/* Turn-by-Turn Transcript & QA Breakdown */}
      <Card style={{ padding: '1.75rem' }}>
        <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0f172a', margin: '0 0 1.25rem 0' }}>
          Question-by-Question Transcript & AI Scoring
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {transcript.map((item, idx) => {
            const diffColor = getDifficultyBadgeColor(item.difficulty);
            const scoreItem = formatScoreBadge(item.score);
            const isFollowup = Boolean(item.is_followup);
            const audioSrc = item.audio_url
              ? (item.audio_url.startsWith('http') ? item.audio_url : `http://localhost:8000/${item.audio_url.replace(/^\//, '')}`)
              : (sessionId && item.question_id ? `http://localhost:8000/api/sessions/${sessionId}/questions/${item.question_id}/audio` : null);

            return (
              <div
                key={item.question_id || idx}
                style={{
                  border: isFollowup ? '1px solid #ddd6fe' : '1px solid #e2e8f0',
                  borderLeft: isFollowup ? '5px solid #8b5cf6' : '4px solid #2563eb',
                  borderRadius: '10px',
                  padding: '1.25rem',
                  backgroundColor: isFollowup ? '#faf5ff' : '#f8fafc',
                  marginLeft: isFollowup ? '2rem' : '0',
                  position: 'relative',
                  transition: 'all 0.2s ease',
                }}
              >
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.85rem', color: isFollowup ? '#7c3aed' : '#2563eb' }}>
                      {isFollowup ? '↳ Follow-Up' : `Q${idx + 1}.`}
                    </span>
                    {isFollowup && (
                      <span style={{
                        fontSize: '0.75rem',
                        fontWeight: 800,
                        backgroundColor: '#ede9fe',
                        color: '#6d28d9',
                        padding: '0.15rem 0.5rem',
                        borderRadius: '9999px',
                        border: '1px solid #c4b5fd',
                      }}>
                        🔍 Dynamic Counter-Question
                      </span>
                    )}
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, backgroundColor: '#e2e8f0', color: '#334155', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                      {item.skill_tag}
                    </span>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, backgroundColor: diffColor.bg, color: diffColor.text, padding: '0.2rem 0.5rem', borderRadius: '9999px', textTransform: 'uppercase' }}>
                      {item.difficulty}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {item.red_flag && (
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, backgroundColor: '#fee2e2', color: '#b91c1c', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                        🚩 Red Flag
                      </span>
                    )}
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, backgroundColor: scoreItem.bg, color: scoreItem.text, padding: '0.25rem 0.6rem', borderRadius: '6px' }}>
                      {scoreItem.label}
                    </span>
                  </div>
                </div>

                {/* Question Text, Avatar Video & Audio Player */}
                <div style={{ marginBottom: '0.75rem' }}>
                  <p style={{ fontWeight: 600, color: '#0f172a', margin: '0 0 0.5rem 0', fontSize: '0.98rem', lineHeight: 1.5 }}>
                    {item.question_text}
                  </p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
                    {item.avatar_video_url && (
                      <video
                        controls
                        playsInline
                        preload="metadata"
                        src={item.avatar_video_url.startsWith('http') ? item.avatar_video_url : `http://localhost:8000/${item.avatar_video_url.replace(/^\//, '')}`}
                        style={{ height: '72px', width: '72px', borderRadius: '8px', objectFit: 'cover', backgroundColor: '#0f172a' }}
                      />
                    )}
                    {audioSrc && (
                      <audio controls src={audioSrc} style={{ height: '32px', width: '240px' }} preload="none" />
                    )}
                  </div>
                </div>

                {/* Candidate Answer */}
                <div style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #cbd5e1',
                  borderRadius: '8px',
                  padding: '0.85rem',
                  marginBottom: '0.75rem',
                  fontSize: '0.9rem',
                  color: '#1e293b',
                  lineHeight: 1.5,
                }}>
                  <strong style={{ color: '#64748b', fontSize: '0.75rem', textTransform: 'uppercase', display: 'block', marginBottom: '0.25rem' }}>
                    Candidate Response:
                  </strong>
                  {item.answer_text || <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>Unanswered</span>}
                </div>

                {/* AI Reasoning */}
                {item.reasoning && (
                  <div style={{ fontSize: '0.85rem', color: '#475569', lineHeight: 1.4, backgroundColor: isFollowup ? '#f5f3ff' : '#ffffff', padding: '0.6rem 0.8rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <strong>AI Evaluation Reasoning:</strong> {item.reasoning}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Full Interview Session Continuous Video (if recorded) */}
      {session_video_url && (
        <Card style={{ marginTop: '1.5rem', padding: '1.75rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0f172a', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>📹</span> Full Interview Video Recording (10-Minute Continuous Session)
          </h2>
          <div style={{
            borderRadius: '12px',
            overflow: 'hidden',
            backgroundColor: '#0f172a',
            maxWidth: '720px',
            margin: '0 auto',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
          }}>
            <video
              src={session_video_url.startsWith('http') ? session_video_url : `http://localhost:8000/${session_video_url.replace(/^\//, '')}`}
              controls
              playsInline
              style={{ width: '100%', maxHeight: '420px', display: 'block' }}
            />
          </div>
        </Card>
      )}

      {/* Proctoring Telemetry Audit Log */}
      {proctoring_events && proctoring_events.length > 0 && (
        <Card style={{ marginTop: '1.5rem', padding: '1.75rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0f172a', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>🛡️</span> Proctoring Telemetry Audit Trail ({proctoring_events.length} event{proctoring_events.length > 1 ? 's' : ''})
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {proctoring_events.map((evt, idx) => {
              const sevBg = evt.severity === 'high' ? '#fee2e2' : evt.severity === 'medium' ? '#fef3c7' : '#f1f5f9';
              const sevColor = evt.severity === 'high' ? '#991b1b' : evt.severity === 'medium' ? '#92400e' : '#475569';
              const proofUrl = evt.screenshot_url
                ? (evt.screenshot_url.startsWith('http') ? evt.screenshot_url : `http://localhost:8000/${evt.screenshot_url.replace(/^\//, '')}`)
                : null;
              const formattedTime = evt.formatted_timestamp || formatDate(evt.timestamp, true);

              return (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.75rem 1rem',
                    borderRadius: '8px',
                    backgroundColor: '#ffffff',
                    border: '1px solid #e2e8f0',
                    flexWrap: 'wrap',
                    gap: '0.5rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      backgroundColor: sevBg,
                      color: sevColor,
                      padding: '0.2rem 0.5rem',
                      borderRadius: '4px',
                    }}>
                      {evt.severity}
                    </span>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <strong style={{ fontSize: '0.9rem', color: '#0f172a' }}>{evt.event_type}</strong>
                        {proofUrl && (
                          <button
                            type="button"
                            onClick={() => setSelectedProofScreenshot({
                              url: proofUrl,
                              title: `${evt.event_type.replace(/_/g, ' ').toUpperCase()} Proof Snapshot`,
                              timestamp: formattedTime,
                            })}
                            style={{
                              fontSize: '0.72rem',
                              fontWeight: 700,
                              color: '#2563eb',
                              backgroundColor: '#eff6ff',
                              border: '1px solid #bfdbfe',
                              borderRadius: '6px',
                              padding: '0.15rem 0.5rem',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                            }}
                          >
                            📷 View Proof Photo
                          </button>
                        )}
                      </div>
                      {evt.details && (
                        <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', color: '#64748b' }}>
                          {evt.details}
                        </p>
                      )}
                    </div>
                  </div>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748b', fontFamily: 'monospace' }}>
                    {formattedTime}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Proof Screenshot Lightbox Modal */}
      {selectedProofScreenshot && (
        <Modal
          isOpen={Boolean(selectedProofScreenshot)}
          onClose={() => setSelectedProofScreenshot(null)}
          title={selectedProofScreenshot.title}
        >
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '1rem' }}>
              Captured at: <strong style={{ color: '#0f172a' }}>{selectedProofScreenshot.timestamp}</strong>
            </p>
            <div style={{
              borderRadius: '12px',
              overflow: 'hidden',
              border: '2px solid #e2e8f0',
              backgroundColor: '#0f172a',
              display: 'inline-block',
              maxWidth: '100%',
            }}>
              <img
                src={selectedProofScreenshot.url}
                alt="Proctoring Infraction Proof"
                style={{ width: '100%', maxHeight: '420px', objectFit: 'contain', display: 'block' }}
              />
            </div>
            <div style={{ marginTop: '1.25rem', display: 'flex', justifyContent: 'flex-end' }}>
              <Button variant="secondary" onClick={() => setSelectedProofScreenshot(null)}>
                Close
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f8fafc', color: '#0f172a' }}>
      <Navbar />
      <Suspense fallback={<div style={{ textAlign: 'center', padding: '3rem' }}>Loading Report...</div>}>
        <ReportContent />
      </Suspense>
    </div>
  );
}
