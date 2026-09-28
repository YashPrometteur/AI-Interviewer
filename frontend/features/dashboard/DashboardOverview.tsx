'use client';
import React from 'react';
import { Card } from '../../components/Card';
import { SessionListItem } from '../../lib/types';

interface DashboardOverviewProps {
  sessions: SessionListItem[];
}

export const DashboardOverview: React.FC<DashboardOverviewProps> = ({ sessions }) => {
  const total = sessions.length;
  const completed = sessions.filter((s) => s.status === 'completed').length;
  const inProgress = sessions.filter((s) => s.status === 'in_progress').length;

  const completedWithScore = sessions.filter((s) => s.status === 'completed' && s.overall_score !== null);
  const avgScore = completedWithScore.length > 0
    ? (completedWithScore.reduce((acc, curr) => acc + (curr.overall_score || 0), 0) / completedWithScore.length).toFixed(1)
    : '—';

  const stats = [
    { label: 'Total Candidates', value: total, icon: '👥', color: '#3b82f6' },
    { label: 'Completed Interviews', value: completed, icon: '✅', color: '#10b981' },
    { label: 'In Progress', value: inProgress, icon: '⏳', color: '#f59e0b' },
    { label: 'Average Score', value: avgScore !== '—' ? `${avgScore} / 10` : '—', icon: '⭐', color: '#8b5cf6' },
  ];

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
      gap: '1.25rem',
      marginBottom: '2rem',
    }}>
      {stats.map((stat, i) => (
        <Card key={i} style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1.25rem' }}>
          <div style={{
            fontSize: '1.75rem',
            width: '48px',
            height: '48px',
            borderRadius: '10px',
            backgroundColor: `${stat.color}15`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            {stat.icon}
          </div>
          <div>
            <div style={{ fontSize: '0.85rem', color: '#64748b', fontWeight: 500 }}>
              {stat.label}
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#0f172a', marginTop: '0.2rem' }}>
              {stat.value}
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};
