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

      <main style={{ maxWidth: '1000px', margin: '0 auto', padding: '4rem 1.5rem', textAlign: 'center' }}>
        {/* Hero Section */}
        <div style={{
          display: 'inline-block',
          backgroundColor: '#eff6ff',
          color: '#2563eb',
          padding: '0.35rem 0.9rem',
          borderRadius: '9999px',
          fontWeight: 700,
          fontSize: '0.85rem',
          marginBottom: '1.25rem',
          letterSpacing: '0.025em',
        }}>
          ⚡ Autonomous AI Technical Interviewer • Phase 1
        </div>

        <h1 style={{
          fontSize: '3rem',
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
            Evaluated by Intelligent AI
          </span>
        </h1>

        <p style={{
          fontSize: '1.2rem',
          color: '#64748b',
          maxWidth: '680px',
          margin: '0 auto 2.5rem auto',
          lineHeight: 1.6,
        }}>
          Upload a Job Description and candidate resume to generate tailored, progressive technical questions.
          Evaluates reasoning, scores answers, and synthesizes executive hiring reports automatically.
        </p>

        {/* Action Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: '1.5rem',
          marginTop: '3rem',
          textAlign: 'left',
        }}>
          {/* Recruiter Portal */}
          <Card style={{
            border: '2px solid #e2e8f0',
            transition: 'all 0.2s ease',
            padding: '2rem',
            borderRadius: '16px',
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>👔</div>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
              Recruiter Dashboard
            </h2>
            <p style={{ color: '#64748b', fontSize: '0.95rem', lineHeight: 1.5, marginBottom: '1.5rem' }}>
              Create interview pipelines, upload JD & candidate resumes, track interview progress, and review comprehensive AI evaluation scorecards.
            </p>
            <Link href="/dashboard" style={{ textDecoration: 'none' }}>
              <Button variant="primary" style={{ width: '100%' }}>
                Open Recruiter Dashboard →
              </Button>
            </Link>
          </Card>

          {/* Candidate Portal */}
          <Card style={{
            border: '2px solid #e2e8f0',
            transition: 'all 0.2s ease',
            padding: '2rem',
            borderRadius: '16px',
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>💻</div>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
              Candidate Interview Room
            </h2>
            <p style={{ color: '#64748b', fontSize: '0.95rem', lineHeight: 1.5, marginBottom: '1.5rem' }}>
              Enter a live text-based technical interview session. Answer progressive technical questions and receive real-time evaluation feedback.
            </p>
            <Link href="/interview" style={{ textDecoration: 'none' }}>
              <Button variant="secondary" style={{ width: '100%' }}>
                Enter Interview Room →
              </Button>
            </Link>
          </Card>
        </div>

        {/* Phase Roadmap Note */}
        <div style={{
          marginTop: '3.5rem',
          padding: '1.25rem',
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          display: 'flex',
          justifyContent: 'space-around',
          flexWrap: 'wrap',
          gap: '1rem',
          fontSize: '0.85rem',
          color: '#475569',
        }}>
          <div><strong>Phase 1:</strong> Text-Based Interview MVP ✅</div>
          <div><strong>Phase 2:</strong> Audio/Video + Async Mode 🔜</div>
          <div><strong>Phase 3:</strong> AI Proctoring & Integrity 🔜</div>
          <div><strong>Phase 4:</strong> Recruiter Auto-Shortlisting 🔜</div>
        </div>
      </main>
    </div>
  );
}
