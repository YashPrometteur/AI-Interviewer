'use client';
import React, { useState } from 'react';
import { Modal } from '../../components/Modal';
import { Button } from '../../components/Button';
import { api } from '../../lib/api';
import { SessionCreateResponse } from '../../lib/types';

interface CreateInterviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSessionCreated: () => void;
}

export const CreateInterviewModal: React.FC<CreateInterviewModalProps> = ({
  isOpen,
  onClose,
  onSessionCreated,
}) => {
  const [candidateName, setCandidateName] = useState('');
  const [candidateEmail, setCandidateEmail] = useState('');
  const [position, setPosition] = useState('');
  const [jdText, setJdText] = useState('');
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [interviewerPhoto, setInterviewerPhoto] = useState<File | null>(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);

  const [interviewMode, setInterviewMode] = useState<'live' | 'async'>('live');
  const [answerCaptureType, setAnswerCaptureType] = useState<'text' | 'video'>('video');
  const [interviewerGender, setInterviewerGender] = useState<'auto' | 'male' | 'female'>('auto');

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [createdSession, setCreatedSession] = useState<SessionCreateResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [emailCopied, setEmailCopied] = useState(false);

  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setInterviewerPhoto(file);
      setPhotoPreviewUrl(URL.createObjectURL(file));
    } else {
      setInterviewerPhoto(null);
      setPhotoPreviewUrl(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!candidateName.trim() || !candidateEmail.trim()) {
      setErrorMessage('Please provide candidate name and email.');
      return;
    }
    if (!position.trim()) {
      setErrorMessage('Please provide the Position / Role applied for.');
      return;
    }
    if (!jdText.trim() || jdText.trim().length < 50) {
      setErrorMessage('Please provide a complete Job Description (minimum 50 characters).');
      return;
    }
    if (!resumeFile) {
      setErrorMessage('Please upload a resume file (.pdf, .docx, or .txt).');
      return;
    }

    try {
      setIsLoading(true);
      const formData = new FormData();
      formData.append('candidate_name', candidateName.trim());
      formData.append('candidate_email', candidateEmail.trim());
      formData.append('position', position.trim());
      formData.append('jd_text', jdText.trim());
      formData.append('resume_file', resumeFile);
      formData.append('interview_mode', interviewMode);
      formData.append('answer_capture_type', answerCaptureType);
      formData.append('interviewer_gender', interviewerGender);
      if (interviewerPhoto) {
        formData.append('interviewer_photo', interviewerPhoto);
      }

      const res = await api.createSession(formData);
      setCreatedSession(res);
      onSessionCreated();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to create interview session.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyLink = () => {
    if (!createdSession) return;
    const fullUrl = typeof window !== 'undefined'
      ? `${window.location.origin}/interview?session_id=${createdSession.session_id}`
      : createdSession.session_url;
    navigator.clipboard.writeText(fullUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  };

  const handleCopyEmail = () => {
    if (!createdSession || !createdSession.email_body) return;
    navigator.clipboard.writeText(createdSession.email_body);
    setEmailCopied(true);
    setTimeout(() => setEmailCopied(false), 3000);
  };

  const handleResetAndClose = () => {
    setCandidateName('');
    setCandidateEmail('');
    setPosition('');
    setJdText('');
    setResumeFile(null);
    setCreatedSession(null);
    setErrorMessage(null);
    setCopied(false);
    setEmailCopied(false);
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleResetAndClose} title="Create AI Interview Session">
      {createdSession ? (
        <div style={{ padding: '0.5rem 0' }}>
          <div style={{ textAlign: 'center', marginBottom: '1.25rem' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>🎉</div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0f172a', margin: '0 0 0.35rem 0' }}>
              Interview Session Generated!
            </h3>
            <p style={{ color: '#64748b', fontSize: '0.9rem', margin: 0 }}>
              {createdSession.total_questions} tailored questions generated for{' '}
              <strong>{createdSession.candidate_name}</strong> ({createdSession.position || position || 'Candidate'}).
            </p>
          </div>

          {/* Email Status Alert Banner */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#f0fdf4',
            border: '1px solid #bbf7d0',
            borderRadius: '8px',
            padding: '0.65rem 0.9rem',
            marginBottom: '1rem',
            fontSize: '0.85rem',
            color: '#166534',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '1.1rem' }}>✉️</span>
              <span>
                Invitation email prepared for <strong>{candidateEmail}</strong> from <strong>Aditi Kumar (HR Head)</strong>
              </span>
            </div>
            <span style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              backgroundColor: '#dcfce7',
              color: '#15803d',
              padding: '0.2rem 0.5rem',
              borderRadius: '9999px',
            }}>
              Prometteur Solutions
            </span>
          </div>

          {/* Direct Link Box */}
          <div style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '0.85rem 1rem',
            marginBottom: '1rem',
            wordBreak: 'break-all',
            fontSize: '0.875rem',
            color: '#0f172a',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <strong>Candidate Direct Test Link:</strong>
              <button
                type="button"
                onClick={handleCopyLink}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#2563eb',
                  fontWeight: 600,
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                {copied ? '✅ Copied' : '📋 Copy URL'}
              </button>
            </div>
            <div style={{ color: '#2563eb', fontFamily: 'monospace', fontSize: '0.85rem' }}>
              {typeof window !== 'undefined' ? `${window.location.origin}/interview?session_id=${createdSession.session_id}` : createdSession.session_url}
            </div>
          </div>

          {/* Email Body Preview & Copy */}
          {createdSession.email_body && (
            <div style={{ marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#334155' }}>
                  📧 Invitation Email Body (Prometteur Solutions)
                </span>
                <button
                  type="button"
                  onClick={handleCopyEmail}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.3rem',
                    padding: '0.25rem 0.6rem',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    backgroundColor: emailCopied ? '#dcfce7' : '#f1f5f9',
                    color: emailCopied ? '#15803d' : '#334155',
                    border: `1px solid ${emailCopied ? '#86efac' : '#cbd5e1'}`,
                    borderRadius: '6px',
                    cursor: 'pointer',
                  }}
                >
                  {emailCopied ? '✅ Email Body Copied!' : '📋 Copy Email Body'}
                </button>
              </div>

              <textarea
                readOnly
                rows={7}
                value={createdSession.email_body}
                style={{
                  width: '100%',
                  padding: '0.65rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#f8fafc',
                  color: '#334155',
                  fontSize: '0.8rem',
                  fontFamily: 'monospace',
                  lineHeight: 1.45,
                  boxSizing: 'border-box',
                  resize: 'vertical',
                }}
              />
            </div>
          )}

          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
            <Button variant="secondary" onClick={handleResetAndClose}>
              Close
            </Button>
            <Button variant="primary" onClick={handleCopyLink}>
              {copied ? '✅ Link Copied!' : '📋 Copy Interview Link'}
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          {errorMessage && (
            <div style={{
              marginBottom: '1rem',
              padding: '0.75rem 1rem',
              backgroundColor: '#fee2e2',
              color: '#b91c1c',
              borderRadius: '8px',
              fontSize: '0.875rem',
            }}>
              ⚠️ {errorMessage}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' }}>
                Candidate Name *
              </label>
              <input
                type="text"
                required
                value={candidateName}
                onChange={(e) => setCandidateName(e.target.value)}
                placeholder="e.g. Alex Rivera"
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.9rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' }}>
                Candidate Email *
              </label>
              <input
                type="email"
                required
                value={candidateEmail}
                onChange={(e) => setCandidateEmail(e.target.value)}
                placeholder="e.g. alex@example.com"
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.9rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </div>

          {/* Position / Role Field (Required before JD) */}
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' }}>
              Position / Role Applied For *
            </label>
            <input
              type="text"
              required
              value={position}
              onChange={(e) => setPosition(e.target.value)}
              placeholder="e.g. Full Stack Python Developer, Senior Frontend Engineer"
              style={{
                width: '100%',
                padding: '0.625rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.9rem',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' }}>
              Job Description (JD) *
            </label>
            <textarea
              rows={5}
              required
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="Paste the full job requirements, skills, and experience criteria..."
              style={{
                width: '100%',
                padding: '0.75rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.9rem',
                boxSizing: 'border-box',
                fontFamily: 'inherit',
              }}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' }}>
                Interview Mode
              </label>
              <select
                value={interviewMode}
                onChange={(e) => setInterviewMode(e.target.value as 'live' | 'async')}
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.9rem',
                  boxSizing: 'border-box',
                  backgroundColor: '#ffffff',
                }}
              >
                <option value="live">⚡ Live Session (Real-time)</option>
                <option value="async">⏳ Async Session (3-day deadline)</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' }}>
                Answer Capture Type
              </label>
              <select
                value={answerCaptureType}
                onChange={(e) => setAnswerCaptureType(e.target.value as 'text' | 'video')}
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.9rem',
                  boxSizing: 'border-box',
                  backgroundColor: '#ffffff',
                }}
              >
                <option value="video">🎥 Video & Audio (Whisper Transcribed)</option>
                <option value="text">📝 Text Input Only</option>
              </select>
            </div>
          </div>

          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' }}>
              Candidate Resume (.PDF, .DOCX, .TXT) *
            </label>
            <input
              type="file"
              required
              accept=".pdf,.docx,.txt"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setResumeFile(e.target.files[0]);
                }
              }}
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px dashed #cbd5e1',
                backgroundColor: '#f8fafc',
                fontSize: '0.85rem',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: '#334155' }}>
                Interviewer Portrait Photo (Optional - Wav2Lip Avatar)
              </label>
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Front-facing portrait (.jpg, .png)</span>
            </div>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={handlePhotoChange}
                style={{
                  flex: 1,
                  padding: '0.5rem',
                  borderRadius: '6px',
                  border: '1px dashed #cbd5e1',
                  backgroundColor: '#f8fafc',
                  fontSize: '0.85rem',
                  boxSizing: 'border-box',
                }}
              />
              {photoPreviewUrl && (
                <div style={{ position: 'relative', width: '48px', height: '48px', borderRadius: '50%', overflow: 'hidden', border: '2px solid #6366f1', flexShrink: 0 }}>
                  <img src={photoPreviewUrl} alt="Interviewer preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
              )}
            </div>
            <p style={{ margin: '0.35rem 0 0.75rem 0', fontSize: '0.75rem', color: '#94a3b8' }}>
              Upload a clear single-person portrait to generate a neural lip-synced interviewer video.
            </p>

            {/* Voice Gender Persona Selector */}
            <div style={{ marginTop: '0.75rem', padding: '0.75rem', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#334155', marginBottom: '0.35rem' }}>
                Interviewer Voice Persona / Gender
              </label>
              <select
                value={interviewerGender}
                onChange={(e) => setInterviewerGender(e.target.value as 'auto' | 'male' | 'female')}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.85rem',
                  boxSizing: 'border-box',
                  backgroundColor: '#ffffff',
                }}
              >
                <option value="auto">🤖 Auto-Match Voice to Photo</option>
                <option value="male">👨 Male Voice (Ryan - Deep & Professional)</option>
                <option value="female">👩 Female Voice (Lessac - Natural & Clear)</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <Button type="button" variant="secondary" onClick={handleResetAndClose} disabled={isLoading}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={isLoading} disabled={isLoading}>
              {isLoading ? 'Generating Interview Bank...' : 'Generate Interview →'}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
};
