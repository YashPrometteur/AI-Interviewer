'use client';
import React, { useEffect, useState } from 'react';
import { Navbar } from '../../components/Navbar';
import { Button } from '../../components/Button';
import { DashboardOverview } from '../../features/dashboard/DashboardOverview';
import { CandidateTable } from '../../features/dashboard/CandidateTable';
import { CreateInterviewModal } from '../../features/dashboard/CreateInterviewModal';
import { api } from '../../lib/api';
import { SessionListItem } from '../../lib/types';

export default function DashboardPage() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const fetchSessions = async () => {
    try {
      setIsLoading(true);
      const data = await api.listSessions();
      setSessions(data);
    } catch (err) {
      console.error('Failed to load interview sessions:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f8fafc', color: '#0f172a' }}>
      <Navbar />

      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '2rem 1.5rem' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '2rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}>
          <div>
            <h1 style={{ fontSize: '1.875rem', fontWeight: 800, color: '#0f172a', margin: 0, letterSpacing: '-0.025em' }}>
              Recruiter Dashboard
            </h1>
            <p style={{ color: '#64748b', fontSize: '0.95rem', margin: '0.25rem 0 0 0' }}>
              Manage candidates, generate automated AI interviews, and review evaluation reports.
            </p>
          </div>

          <Button variant="primary" onClick={() => setIsModalOpen(true)}>
            + Create New Interview
          </Button>
        </div>

        <DashboardOverview sessions={sessions} />

        <CandidateTable
          sessions={sessions}
          isLoading={isLoading}
          onRefresh={fetchSessions}
        />

        <CreateInterviewModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          onSessionCreated={fetchSessions}
        />
      </main>
    </div>
  );
}
