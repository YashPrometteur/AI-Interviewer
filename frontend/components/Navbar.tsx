'use client';
import React from 'react';
import Link from 'next/link';

export const Navbar = () => {
  return (
    <header style={{
      backgroundColor: '#ffffff',
      borderBottom: '1px solid #e2e8f0',
      padding: '1rem 2rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 40,
      boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Link href="/" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', textDecoration: 'none' }}>
          <div style={{
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 'bold',
            fontSize: '1.1rem'
          }}>
            AI
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0f172a', letterSpacing: '-0.025em' }}>
            AI Interviewer
          </span>
        </Link>
        <span style={{
          backgroundColor: '#eff6ff',
          color: '#2563eb',
          fontSize: '0.75rem',
          padding: '0.2rem 0.6rem',
          borderRadius: '9999px',
          fontWeight: 600
        }}>
          Phase 1 MVP
        </span>
      </div>

      <nav style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
        <Link href="/dashboard" style={{
          fontSize: '0.925rem',
          fontWeight: 500,
          color: '#475569',
          textDecoration: 'none',
          padding: '0.4rem 0.8rem',
          borderRadius: '6px',
          transition: 'all 0.15s ease'
        }}>
          Recruiter Dashboard
        </Link>
        <Link href="/interview" style={{
          fontSize: '0.925rem',
          fontWeight: 500,
          color: '#475569',
          textDecoration: 'none',
          padding: '0.4rem 0.8rem',
          borderRadius: '6px'
        }}>
          Candidate Room
        </Link>
      </nav>
    </header>
  );
};
