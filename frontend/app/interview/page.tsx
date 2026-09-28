'use client';
import React, { Suspense, useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { Navbar } from '../../components/Navbar';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { InterviewRoom } from '../../features/interview/InterviewRoom';
import { api } from '../../lib/api';
import { SessionListItem } from '../../lib/types';

function InterviewContent() {
  const searchParams = useSearchParams();
  const querySessionId = searchParams.get('session_id');

  const [inputSessionId, setInputSessionId] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(querySessionId);
  const [availableSessions, setAvailableSessions] = useState<SessionListItem[]>([]);

  useEffect(() => {
    if (querySessionId) {
      setActiveSessionId(querySessionId);
    } else {
      // Load recent sessions to help user jump into an interview quickly
      api.listSessions().then((list) => {
        setAvailableSessions(list.filter((s) => s.status !== 'completed'));
      }).catch(() => {});
    }
  }, [querySessionId]);

  if (activeSessionId) {
    return <InterviewRoom sessionId={activeSessionId} />;
  }

  return (
    <div style={{ maxWidth: '650px', margin: '3rem auto', padding: '0 1rem' }}>
      <Card>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>🎯</div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#0f172a', margin: '0 0 0.5rem 0' }}>
            Enter Candidate Interview Room
          </h2>
          <p style={{ color: '#64748b', fontSize: '0.9rem', margin: 0 }}>
            Enter your unique Interview Session ID to begin your technical interview.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (inputSessionId.trim()) {
              setActiveSessionId(inputSessionId.trim());
            }
          }}
          style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}
        >
          <input
            type="text"
            required
            value={inputSessionId}
            onChange={(e) => setInputSessionId(e.target.value)}
            placeholder="Paste Session ID (e.g. 5456619a-...)"
            style={{
              flex: 1,
              padding: '0.625rem 0.85rem',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '0.9rem',
              outline: 'none',
            }}
          />
          <Button type="submit" variant="primary">
            Start Interview →
          </Button>
        </form>

        {availableSessions.length > 0 && (
          <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1.25rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748b', marginBottom: '0.75rem', textTransform: 'uppercase' }}>
              Or Select An Active Pending Session:
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {availableSessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => setActiveSessionId(s.id)}
                  style={{
                    padding: '0.75rem 1rem',
                    backgroundColor: '#f8fafc',
                    borderRadius: '8px',
                    border: '1px solid #e2e8f0',
                    cursor: 'pointer',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, color: '#0f172a', fontSize: '0.9rem' }}>{s.candidate_name}</div>
                    <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{s.candidate_email}</div>
                  </div>
                  <span style={{ fontSize: '0.8rem', color: '#2563eb', fontWeight: 600 }}>
                    Enter Room →
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

export default function InterviewPage() {
  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f8fafc', color: '#0f172a' }}>
      <Navbar />
      <Suspense fallback={<div style={{ textAlign: 'center', padding: '3rem' }}>Loading Interview Session...</div>}>
        <InterviewContent />
      </Suspense>
    </div>
  );
}
