import React, { useState } from 'react';
import { api } from '../../api';
import Icon from '../icons';

const EmailVerificationBanner = ({ user }) => {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  if (!user || user.email_verified_at) return null;

  const resend = async () => {
    setSending(true);
    setError('');
    try {
      await api.resendVerification();
      setSent(true);
    } catch (e) {
      setError(e.message || 'Не удалось отправить письмо');
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '0.75rem',
      flexWrap: 'wrap',
      padding: '0.6rem 1rem',
      background: 'rgba(245, 158, 11, 0.12)',
      borderBottom: '1px solid rgba(245, 158, 11, 0.35)',
      color: '#f59e0b',
      fontSize: '0.88rem',
    }}>
      <span>
        <Icon name="warning" size={18} />
        <span>Подтвердите email <strong>{user.email}</strong> — без этого мы не сможем восстановить доступ к аккаунту.</span>
      </span>
      <button
        onClick={resend}
        disabled={sending || sent}
        style={{
          background: 'transparent',
          border: '1px solid #f59e0b',
          color: '#f59e0b',
          borderRadius: 6,
          padding: '0.25rem 0.75rem',
          cursor: sending || sent ? 'default' : 'pointer',
          fontSize: '0.85rem',
        }}
      >
        {sent ? 'Письмо отправлено ✅' : sending ? 'Отправляем…' : 'Отправить письмо снова'}
      </button>
      {error && <span style={{ color: '#ef4444' }}>{error}</span>}
    </div>
  );
};

export default EmailVerificationBanner;