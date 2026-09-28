'use client';
import React, { useState, useMemo, useEffect } from 'react';
import Link from 'next/link';
import { Card } from '../../components/Card';
import { SessionListItem } from '../../lib/types';
import { formatScoreBadge, formatDate } from '../../lib/utils';

interface CandidateTableProps {
  sessions: SessionListItem[];
  isLoading: boolean;
  onRefresh: () => void;
}

export const CandidateTable: React.FC<CandidateTableProps> = ({ sessions, isLoading, onRefresh }) => {
  const [currentPage, setCurrentPage] = useState<number>(1);
  const pageSize = 5;

  // Ensure latest entries always appear first
  const sortedSessions = useMemo(() => {
    return [...sessions].sort((a, b) => {
      const dateA = new Date(a.created_at || 0).getTime();
      const dateB = new Date(b.created_at || 0).getTime();
      return dateB - dateA;
    });
  }, [sessions]);

  const totalPages = Math.max(1, Math.ceil(sortedSessions.length / pageSize));

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [totalPages, currentPage]);

  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, sortedSessions.length);
  const displayedSessions = sortedSessions.slice(startIndex, endIndex);

  return (
    <Card style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{
        padding: '1.25rem 1.5rem',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#0f172a' }}>
            Candidate Interview Pipeline
          </h3>
          <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', color: '#64748b' }}>
            Latest interviews displayed first • Showing 5 entries per page
          </p>
        </div>
        <button
          onClick={() => {
            setCurrentPage(1);
            onRefresh();
          }}
          disabled={isLoading}
          style={{
            background: 'none',
            border: '1px solid #cbd5e1',
            padding: '0.4rem 0.8rem',
            borderRadius: '6px',
            fontSize: '0.85rem',
            cursor: 'pointer',
            color: '#475569',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
          }}
        >
          {isLoading ? 'Refreshing...' : '🔄 Refresh'}
        </button>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontWeight: 600 }}>
              <th style={{ padding: '0.85rem 1.25rem' }}>Candidate</th>
              <th style={{ padding: '0.85rem 1.25rem' }}>Status</th>
              <th style={{ padding: '0.85rem 1.25rem' }}>Progress</th>
              <th style={{ padding: '0.85rem 1.25rem' }}>Score</th>
              <th style={{ padding: '0.85rem 1.25rem' }}>Integrity</th>
              <th style={{ padding: '0.85rem 1.25rem' }}>Created Date</th>
              <th style={{ padding: '0.85rem 1.25rem', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedSessions.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: '3.5rem', textAlign: 'center', color: '#64748b' }}>
                  <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📂</div>
                  <div>No interview sessions found yet.</div>
                  <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: '0.25rem' }}>
                    Click <strong>"+ Create New Interview"</strong> above to generate a new candidate session.
                  </div>
                </td>
              </tr>
            ) : (
              displayedSessions.map((s) => {
                const scoreBadge = formatScoreBadge(s.overall_score);
                const isCompleted = s.status === 'completed';
                const proctoringBadge = isCompleted
                  ? { label: 'Recorded 🛡️', bg: '#ecfdf5', text: '#047857' }
                  : { label: 'Active 📹', bg: '#f1f5f9', text: '#475569' };

                return (
                  <tr
                    key={s.id}
                    style={{
                      borderBottom: '1px solid #f1f5f9',
                      transition: 'background-color 0.15s ease',
                    }}
                  >
                    <td style={{ padding: '1rem 1.25rem' }}>
                      <div style={{ fontWeight: 600, color: '#0f172a' }}>{s.candidate_name}</div>
                      <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{s.candidate_email}</div>
                    </td>

                    <td style={{ padding: '1rem 1.25rem' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '0.2rem 0.6rem',
                        borderRadius: '9999px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        backgroundColor: isCompleted ? '#dcfce7' : s.status === 'in_progress' ? '#fef3c7' : '#f1f5f9',
                        color: isCompleted ? '#15803d' : s.status === 'in_progress' ? '#b45309' : '#475569',
                      }}>
                        {s.status.replace('_', ' ')}
                      </span>
                    </td>

                    <td style={{ padding: '1rem 1.25rem', color: '#475569' }}>
                      {s.answered_questions} / {s.total_questions} questions
                    </td>

                    <td style={{ padding: '1rem 1.25rem' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '0.25rem 0.6rem',
                        borderRadius: '6px',
                        fontWeight: 700,
                        fontSize: '0.85rem',
                        backgroundColor: scoreBadge.bg,
                        color: scoreBadge.text,
                      }}>
                        {scoreBadge.label}
                      </span>
                    </td>

                    <td style={{ padding: '1rem 1.25rem' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '0.25rem 0.6rem',
                        borderRadius: '6px',
                        fontWeight: 700,
                        fontSize: '0.85rem',
                        backgroundColor: proctoringBadge.bg,
                        color: proctoringBadge.text,
                      }}>
                        {proctoringBadge.label}
                      </span>
                    </td>

                    <td style={{ padding: '1rem 1.25rem', color: '#64748b', fontSize: '0.85rem' }}>
                      {formatDate(s.created_at)}
                    </td>

                    <td style={{ padding: '1rem 1.25rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        {isCompleted ? (
                          <Link
                            href={`/reports?session_id=${s.id}`}
                            style={{
                              backgroundColor: '#2563eb',
                              color: '#fff',
                              padding: '0.35rem 0.75rem',
                              borderRadius: '6px',
                              textDecoration: 'none',
                              fontSize: '0.8rem',
                              fontWeight: 600,
                            }}
                          >
                            View Report 📄
                          </Link>
                        ) : (
                          <Link
                            href={`/interview?session_id=${s.id}`}
                            style={{
                              backgroundColor: '#f1f5f9',
                              color: '#0f172a',
                              border: '1px solid #cbd5e1',
                              padding: '0.35rem 0.75rem',
                              borderRadius: '6px',
                              textDecoration: 'none',
                              fontSize: '0.8rem',
                              fontWeight: 600,
                            }}
                          >
                            Interview Link 🔗
                          </Link>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* 5-Per-Page Maneuverable Pagination Footer */}
      {sortedSessions.length > 0 && (
        <div style={{
          padding: '1rem 1.5rem',
          backgroundColor: '#f8fafc',
          borderTop: '1px solid #e2e8f0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}>
          <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
            Showing <strong>{startIndex + 1}</strong>–<strong>{endIndex}</strong> of <strong>{sortedSessions.length}</strong> candidates
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            {/* Prev Page */}
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              style={{
                padding: '0.35rem 0.75rem',
                fontSize: '0.85rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: currentPage === 1 ? '#f1f5f9' : '#ffffff',
                color: currentPage === 1 ? '#94a3b8' : '#334155',
                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              ← Prev
            </button>

            {/* Page Numbers */}
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => (
              <button
                key={pageNum}
                onClick={() => setCurrentPage(pageNum)}
                style={{
                  minWidth: '32px',
                  height: '32px',
                  padding: '0 0.5rem',
                  fontSize: '0.85rem',
                  borderRadius: '6px',
                  border: pageNum === currentPage ? '1px solid #2563eb' : '1px solid #cbd5e1',
                  backgroundColor: pageNum === currentPage ? '#2563eb' : '#ffffff',
                  color: pageNum === currentPage ? '#ffffff' : '#334155',
                  cursor: 'pointer',
                  fontWeight: pageNum === currentPage ? 700 : 500,
                  transition: 'all 0.15s ease',
                }}
              >
                {pageNum}
              </button>
            ))}

            {/* Next Page */}
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              style={{
                padding: '0.35rem 0.75rem',
                fontSize: '0.85rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: currentPage === totalPages ? '#f1f5f9' : '#ffffff',
                color: currentPage === totalPages ? '#94a3b8' : '#334155',
                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </Card>
  );
};
