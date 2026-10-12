import React, { useEffect, useState } from 'react';
import { api } from '../api';
import Icon from '../components/icons';

const WRAP = { maxWidth: 460, margin: '5rem auto', padding: '0 1.5rem' };
const CARD = {
  padding: '2rem',
  borderRadius: 12,
  background: 'var(--bg-secondary, #171a26)',
  border: '1px solid var(--border, #2a2e3d)',
  textAlign: 'center',
};
const TITLE = { marginBottom: '0.75rem', fontSize: '1.4rem' };
const TEXT = {
  color: 'var(--text-secondary)',
  fontSize: '0.92rem',
  lineHeight: 1.6,
  marginBottom: '1.25rem',
};
const LINK = { color: 'var(--accent-primary)', textDecoration: 'none' };

const Shell = ({ children }) => (
  <div className="public-layout">
    <div style={WRAP}>
      <div style={CARD}>{children}</div>
      <p style={{ textAlign: 'center', marginTop: '1.25rem', fontSize: '0.85rem' }}>
        <a href="#/" style={LINK}>
          ← На главную
        </a>
      </p>
    </div>
  </div>
);

/* ============================================================
   Подтверждение email: #/verify-email?token=...
   ============================================================ */
export const VerifyEmailPage = ({ token }) => {
  const [state, setState] = useState(token ? 'loading' : 'error');
  const [message, setMessage] = useState(token ? '' : 'Ссылка не содержит токен подтверждения.');

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .verifyEmail(token)
      .then((data) => {
        if (cancelled) return;
        setState('success');
        setMessage(data.message || 'Email подтверждён.');
      })
      .catch((err) => {
        if (cancelled) return;
        setState('error');
        setMessage(err.message || 'Не удалось подтвердить email.');
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <Shell>
      {state === 'loading' && (
        <>
          <h1
            style={{
              ...TITLE,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
            }}
          >
            <span style={{ color: 'var(--accent-primary)', display: 'inline-flex' }}>
              <Icon name="refresh" size={26} />
            </span>
            Подтверждаем email…
          </h1>
          <p style={TEXT}>Подождите, это займёт пару секунд.</p>
        </>
      )}
      {state === 'success' && (
        <>
          <h1
            style={{
              ...TITLE,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
            }}
          >
            <span style={{ color: 'var(--accent-success)', display: 'inline-flex' }}>
              <Icon name="export" size={26} />
            </span>
            Email подтверждён
          </h1>
          <p style={TEXT}>{message}</p>
          <a href="#/" className="btn btn-primary" style={{ display: 'inline-block' }}>
            Войти в сервис
          </a>
        </>
      )}
      {state === 'error' && (
        <>
          <h1 style={TITLE}>❌ Не удалось подтвердить</h1>
          <p style={TEXT}>
            {message} Возможно, ссылка просрочена (действует 24 часа). Войдите в аккаунт — в шапке
            будет кнопка «Отправить письмо снова».
          </p>
          <a href="#/" className="btn btn-primary" style={{ display: 'inline-block' }}>
            Войти
          </a>
        </>
      )}
    </Shell>
  );
};

/* ============================================================
   Запрос сброса пароля: #/forgot-password
   ============================================================ */
export const ForgotPasswordPage = () => {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await api.forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      setError(err.message || 'Ошибка отправки');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Shell>
      <h1
        style={{
          ...TITLE,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0.5rem',
        }}
      >
        <span style={{ color: 'var(--accent-primary)', display: 'inline-flex' }}>
          <Icon name="key" size={26} />
        </span>
        Восстановление пароля
      </h1>
      {sent ? (
        <p style={TEXT}>
          Если адрес <strong>{email}</strong> зарегистрирован, мы отправили на него ссылку для
          сброса пароля. Письмо действует 1 час. Проверьте папку «Спам», если письма нет во
          «Входящих».
        </p>
      ) : (
        <form onSubmit={submit} style={{ textAlign: 'left' }}>
          <label className="form-label">Email</label>
          <input
            className="form-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@mail.ru"
            required
          />
          {error && (
            <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
              {error}
            </div>
          )}
          <div style={{ marginTop: '1.25rem', textAlign: 'center' }}>
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? 'Отправляем…' : 'Отправить ссылку'}
            </button>
          </div>
        </form>
      )}
      <p style={{ ...TEXT, marginTop: '1.25rem', marginBottom: 0 }}>
        Вспомнили пароль?{' '}
        <a href="#/" style={LINK}>
          Войти
        </a>
      </p>
    </Shell>
  );
};

/* ============================================================
   Сброс пароля: #/reset-password?token=...
   ============================================================ */
export const ResetPasswordPage = ({ token }) => {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 6) {
      setError('Пароль должен содержать минимум 6 символов');
      return;
    }
    if (password !== confirm) {
      setError('Пароли не совпадают');
      return;
    }
    setLoading(true);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(err.message || 'Не удалось сбросить пароль');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <Shell>
        <h1 style={TITLE}>❌ Ссылка недействительна</h1>
        <p style={TEXT}>В ссылке нет токена сброса. Запросите сброс заново.</p>
        <a href="#/forgot-password" className="btn btn-primary" style={{ display: 'inline-block' }}>
          Запросить сброс
        </a>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1
        style={{
          ...TITLE,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0.5rem',
        }}
      >
        <span style={{ color: 'var(--accent-primary)', display: 'inline-flex' }}>
          <Icon name="lock" size={26} />
        </span>
        Новый пароль
      </h1>
      {done ? (
        <>
          <p style={TEXT}>Пароль изменён. Войдите с новым паролем.</p>
          <a href="#/" className="btn btn-primary" style={{ display: 'inline-block' }}>
            Войти
          </a>
        </>
      ) : (
        <form onSubmit={submit} style={{ textAlign: 'left' }}>
          <label className="form-label">Новый пароль</label>
          <input
            className="form-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Минимум 6 символов"
            required
          />
          <label className="form-label">Повторите пароль</label>
          <input
            className="form-input"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Ещё раз"
            required
          />
          {error && (
            <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
              {error}
            </div>
          )}
          <div style={{ marginTop: '1.25rem', textAlign: 'center' }}>
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? 'Сохраняем…' : 'Сменить пароль'}
            </button>
          </div>
        </form>
      )}
    </Shell>
  );
};
