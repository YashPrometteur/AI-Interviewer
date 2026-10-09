'use client';
import React, { useState } from 'react';
import { Button } from '../../components/Button';

interface AnswerInputProps {
  onSubmit: (answerText: string) => Promise<void>;
  isLoading: boolean;
}

export const AnswerInput: React.FC<AnswerInputProps> = ({ onSubmit, isLoading }) => {
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const textToSubmit = answer.trim() || '[No answer provided]';
    setError(null);
    try {
      await onSubmit(textToSubmit);
      setAnswer('');
    } catch (err: any) {
      setError(err.message || 'Failed to submit answer. Please try again.');
    }
  };

  const wordCount = answer.trim() ? answer.trim().split(/\s+/).length : 0;
  const charCount = answer.length;

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: '1rem' }}>
      <div style={{ position: 'relative' }}>
        <textarea
          rows={7}
          value={answer}
          disabled={isLoading}
          onChange={(e) => {
            setAnswer(e.target.value);
            if (error) setError(null);
          }}
          placeholder="Type your technical answer here in detail. Explain your reasoning, trade-offs, and examples..."
          style={{
            width: '100%',
            padding: '1rem',
            fontSize: '1rem',
            lineHeight: 1.5,
            borderRadius: '10px',
            border: error ? '2px solid #ef4444' : '1px solid #cbd5e1',
            outline: 'none',
            fontFamily: 'inherit',
            resize: 'vertical',
            backgroundColor: isLoading ? '#f8fafc' : '#ffffff',
            boxSizing: 'border-box',
            boxShadow: 'inset 0 1px 2px 0 rgba(0, 0, 0, 0.05)',
          }}
        />

        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: '0.5rem',
          fontSize: '0.8rem',
          color: '#64748b',
        }}>
          <div>
            <span>{wordCount} words</span> • <span>{charCount} characters</span>
          </div>
          {wordCount > 0 && wordCount < 10 && (
            <span style={{ color: '#d97706' }}>Tip: Provide more depth for a higher evaluation score.</span>
          )}
        </div>
      </div>

      {error && (
        <div style={{
          marginTop: '0.75rem',
          padding: '0.75rem 1rem',
          backgroundColor: '#fee2e2',
          color: '#b91c1c',
          borderRadius: '8px',
          fontSize: '0.875rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}>
          ⚠️ {error}
        </div>
      )}

      <div style={{ marginTop: '1.25rem', display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
        <Button
          type="submit"
          variant="primary"
          isLoading={isLoading}
          disabled={isLoading}
          style={{ padding: '0.75rem 2rem', fontSize: '1rem' }}
        >
          {isLoading ? 'Evaluating Answer...' : 'Submit Answer & Continue →'}
        </Button>
      </div>
    </form>
  );
};
