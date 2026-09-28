'use client';
import React from 'react';

interface CardProps {
  children: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({ children, style, className, onClick }) => {
  return (
    <div
      className={className}
      onClick={onClick}
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        padding: '1.5rem',
        boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)',
        ...style,
      }}
    >
      {children}
    </div>
  );
};
