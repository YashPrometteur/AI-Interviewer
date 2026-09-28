'use client';
import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'outline';
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  isLoading = false,
  disabled,
  style,
  ...props
}) => {
  let bg = '#2563eb';
  let color = '#ffffff';
  let border = '1px solid transparent';

  if (variant === 'secondary') {
    bg = '#f1f5f9';
    color = '#0f172a';
    border = '1px solid #cbd5e1';
  } else if (variant === 'danger') {
    bg = '#dc2626';
    color = '#ffffff';
  } else if (variant === 'outline') {
    bg = 'transparent';
    color = '#2563eb';
    border = '1px solid #2563eb';
  }

  return (
    <button
      disabled={disabled || isLoading}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.5rem',
        backgroundColor: disabled || isLoading ? '#94a3b8' : bg,
        color: color,
        border: border,
        padding: '0.625rem 1.25rem',
        borderRadius: '8px',
        fontSize: '0.9rem',
        fontWeight: 600,
        cursor: disabled || isLoading ? 'not-allowed' : 'pointer',
        transition: 'all 0.15s ease',
        boxShadow: variant === 'primary' ? '0 1px 2px 0 rgba(0, 0, 0, 0.05)' : 'none',
        ...style,
      }}
      {...props}
    >
      {isLoading && (
        <span style={{
          display: 'inline-block',
          width: '14px',
          height: '14px',
          border: '2px solid rgba(255,255,255,0.3)',
          borderTopColor: '#ffffff',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }} />
      )}
      {children}
    </button>
  );
};
