'use client';
import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export const Navbar = () => {
  const pathname = usePathname();

  return (
    <header style={{
      backgroundColor: '#ffffff',
      borderBottom: '1px solid #e2e8f0',
      padding: '0.9rem 2rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 40,
      boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Link href="/" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', textDecoration: 'none' }}>
          <div style={{
            width: '34px',
            height: '34px',
            borderRadius: '9px',
            background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 800,
            fontSize: '1rem',
            boxShadow: '0 2px 4px rgba(37, 99, 235, 0.25)',
          }}>
            AI
          </div>
          <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.025em' }}>
            AI Interviewer
          </span>
        </Link>
      </div>

      <nav style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <Link
          href="/dashboard"
          style={{
            fontSize: '0.9rem',
            fontWeight: 600,
            color: pathname === '/dashboard' ? '#2563eb' : '#475569',
            backgroundColor: pathname === '/dashboard' ? '#eff6ff' : 'transparent',
            textDecoration: 'none',
            padding: '0.45rem 0.9rem',
            borderRadius: '8px',
            transition: 'all 0.15s ease'
          }}
        >
          Recruiter Dashboard
        </Link>
        <Link
          href="/interview"
          style={{
            fontSize: '0.9rem',
            fontWeight: 600,
            color: pathname?.startsWith('/interview') ? '#2563eb' : '#475569',
            backgroundColor: pathname?.startsWith('/interview') ? '#eff6ff' : 'transparent',
            textDecoration: 'none',
            padding: '0.45rem 0.9rem',
            borderRadius: '8px',
            transition: 'all 0.15s ease'
          }}
        >
          Candidate Room
        </Link>
      </nav>
    </header>
  );
};

