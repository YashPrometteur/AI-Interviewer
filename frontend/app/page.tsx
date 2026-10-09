'use client';
import React from 'react';
import Link from 'next/link';
import { Navbar } from '../components/Navbar';
import { Card } from '../components/Card';
import { Button } from '../components/Button';

export default function HomePage() {
  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f8fafc', color: '#0f172a' }}>
      <Navbar />

      <main style={{ maxWidth: '1080px', margin: '0 auto', padding: '4rem 1.5rem', textAlign: 'center' }}>
        {/* Sleek Pill Badge */}
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.4rem',
          backgroundColor: '#eff6ff',
          color: '#2563eb',
          padding: '0.35rem 0.95rem',
          borderRadius: '9999px',
          fontWeight: 700,
          fontSize: '0.825rem',
          marginBottom: '1.5rem',
          letterSpacing: '0.025em',
          border: '1px solid #dbeafe',
        }}>
          <span>✨</span> Enterprise AI Technical Screening Platform
        </div>

        <h1 style={{
          fontSize: '3.25rem',
          fontWeight: 900,
          color: '#0f172a',
          margin: '0 0 1.25rem 0',
          letterSpacing: '-0.035em',
          lineHeight: 1.15,
        }}>
          Hire Top Engineering Talent <br />
          <span style={{
            background: 'linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>
            Evaluated by Autonomous AI
          </span>
        </h1>

        <p style={{
          fontSize: '1.15rem',
          color: '#64748b',
          maxWidth: '720px',
          margin: '0 auto 3rem auto',
          lineHeight: 1.6,
        }}>
          Upload a Job Description and candidate resume to generate tailored, progressive technical assessments.
          Conducts video & voice interviews, analyzes technical reasoning, and generates objective scorecards automatically.
        </p>

        {/* Action Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '1.75rem',
          textAlign: 'left',
          marginBottom: '3.5rem',
        }}>
          {/* Recruiter Portal */}
          <Card style={{
            border: '1px solid #e2e8f0',
            boxShadow: '0 4px 12px -2px rgba(0, 0, 0, 0.05)',
            padding: '2.25rem',
            borderRadius: '16px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}>
            <div>
              <div style={{
                width: '48px',
                height: '48px',
                borderRadius: '12px',
                backgroundColor: '#eff6ff',
                color: '#2563eb',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.5rem',
                marginBottom: '1.25rem',
              }}>
                👔
              </div>
              <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#0f172a', marginBottom: '0.5rem' }}>
                Recruiter Dashboard
              </h2>
              <p style={{ color: '#64748b', fontSize: '0.925rem', lineHeight: 1.55, marginBottom: '1.75rem' }}>
                Create interview pipelines, upload JD & candidate resumes, track interview progress, and review comprehensive AI evaluation scorecards.
              </p>
            </div>
            <Link href="/dashboard" style={{ textDecoration: 'none' }}>
              <Button variant="primary" style={{ width: '100%', padding: '0.75rem 1.25rem', fontWeight: 700 }}>
                Open Recruiter Dashboard →
              </Button>
            </Link>
          </Card>

          {/* Candidate Portal */}
          <Card style={{
            border: '1px solid #e2e8f0',
            boxShadow: '0 4px 12px -2px rgba(0, 0, 0, 0.05)',
            padding: '2.25rem',
            borderRadius: '16px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}>
            <div>
              <div style={{
                width: '48px',
                height: '48px',
                borderRadius: '12px',
                backgroundColor: '#f5f3ff',
                color: '#7c3aed',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.5rem',
                marginBottom: '1.25rem',
              }}>
                💻
              </div>
              <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#0f172a', marginBottom: '0.5rem' }}>
                Candidate Interview Room
              </h2>
              <p style={{ color: '#64748b', fontSize: '0.925rem', lineHeight: 1.55, marginBottom: '1.75rem' }}>
                Enter a live technical interview session. Answer progressive technical questions via video/audio and receive automated evaluation feedback.
              </p>
            </div>
            <Link href="/interview" style={{ textDecoration: 'none' }}>
              <Button variant="secondary" style={{ width: '100%', padding: '0.75rem 1.25rem', fontWeight: 700 }}>
                Enter Candidate Room →
              </Button>
            </Link>
          </Card>
        </div>

        {/* Feature Highlights Grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1.25rem',
          padding: '1.75rem',
          backgroundColor: '#ffffff',
          borderRadius: '16px',
          border: '1px solid #e2e8f0',
          textAlign: 'left',
        }}>
          <div>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.35rem' }}>🎯</div>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a', margin: '0 0 0.25rem 0' }}>Adaptive Counter-Questions</h3>
            <p style={{ fontSize: '0.825rem', color: '#64748b', margin: 0, lineHeight: 1.45 }}>Dynamic follow-ups probe candidate depth and clarify ambiguous responses in real time.</p>
          </div>
          <div>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.35rem' }}>🎙️</div>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a', margin: '0 0 0.25rem 0' }}>Neural Voice & Avatars</h3>
            <p style={{ fontSize: '0.825rem', color: '#64748b', margin: 0, lineHeight: 1.45 }}>Low-latency Piper TTS audio streaming and lifelike Wav2Lip interviewer lip-sync.</p>
          </div>
          <div>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.35rem' }}>🛡️</div>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a', margin: '0 0 0.25rem 0' }}>AI Proctoring & Integrity</h3>
            <p style={{ fontSize: '0.825rem', color: '#64748b', margin: 0, lineHeight: 1.45 }}>Real-time face verification, multi-person alerts, and device detection audit trail.</p>
          </div>
          <div>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.35rem' }}>📊</div>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a', margin: '0 0 0.25rem 0' }}>Objective Scorecards</h3>
            <p style={{ fontSize: '0.825rem', color: '#64748b', margin: 0, lineHeight: 1.45 }}>Comprehensive rubric scoring with printable reports and full session recording playback.</p>
          </div>
        </div>
      </main>
    </div>
  );
}

