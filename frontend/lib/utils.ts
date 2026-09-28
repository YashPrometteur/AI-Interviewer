// Phase 1: Shared UI helper utilities for badges, score colors, formatting, and recommendations.

export function formatScoreBadge(score: number | null | undefined): { label: string; bg: string; text: string } {
  if (score === null || score === undefined) {
    return { label: 'Pending', bg: '#f1f5f9', text: '#64748b' };
  }
  if (score >= 7.5) {
    return { label: `${score.toFixed(1)}/10`, bg: '#dcfce7', text: '#15803d' };
  }
  if (score >= 5.0) {
    return { label: `${score.toFixed(1)}/10`, bg: '#fef3c7', text: '#b45309' };
  }
  return { label: `${score.toFixed(1)}/10`, bg: '#fee2e2', text: '#b91c1c' };
}

export function formatRecommendationBadge(recommendation: string | undefined): { label: string; bg: string; text: string } {
  const rec = (recommendation || '').toLowerCase();
  if (rec === 'pass') {
    return { label: 'PASS (HIRE)', bg: '#10b981', text: '#ffffff' };
  }
  if (rec === 'borderline') {
    return { label: 'BORDERLINE (HOLD)', bg: '#f59e0b', text: '#ffffff' };
  }
  return { label: 'FAIL (NO HIRE)', bg: '#ef4444', text: '#ffffff' };
}

export function getDifficultyBadgeColor(difficulty: string | null | undefined): { bg: string; text: string } {
  const diff = (difficulty || 'medium').toLowerCase();
  switch (diff) {
    case 'easy':
      return { bg: '#e0f2fe', text: '#0369a1' };
    case 'hard':
      return { bg: '#fce7f3', text: '#be185d' };
    case 'medium':
    default:
      return { bg: '#fef3c7', text: '#b45309' };
  }
}

export function formatDate(dateString: string | null | undefined, includeSeconds: boolean = true): string {
  if (!dateString) return '—';
  try {
    const d = new Date(dateString);
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      ...(includeSeconds ? { second: '2-digit' } : {}),
    });
  } catch {
    return dateString;
  }
}
