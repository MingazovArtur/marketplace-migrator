import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import { api } from '../../api';
import Icon from '../icons';

const AuthModal = ({ isOpen, initialTab = 'login', onClose, onLogin }) => {
  const [tab, setTab] = useState(initialTab);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [agree, setAgree] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');

  useEffect(() => {
    if (isOpen) {
      setTab(initialTab);
      setError('');
      setAgree(false);          // ✅ сбрасываем согласие при открытии
      setUsername('');
      setPassword('');
      setRegEmail('');
      setRegUsername('');
      setRegPassword('');
    }
  }, [isOpen, initialTab]);

  if (!isOpen) return null;

  const submitLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    console.log('🔐 Вход:', { username, password: '***' });

    try {
      const data = await api.login({ username: username.trim(), password });
      console.log('✅ Вход выполнен:', data);
      onLogin(data.access_token);
      onClose();
    } catch (err) {
      console.error('❌ Ошибка входа:', err);
      setError(err.message || 'Неверный логин или пароль');
    } finally {
      setLoading(false);
    }
  };

  const submitRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // Валидация на клиенте
    if (!regEmail || !regEmail.includes('@')) {
      setError('Введите корректный email');
      setLoading(false);
      return;
    }
    if (!regUsername || regUsername.length < 3) {
      setError('Логин должен содержать минимум 3 символа');
      setLoading(false);
      return;
    }
    if (!regPassword || regPassword.length < 6) {
      setError('Пароль должен содержать минимум 6 символов');
      setLoading(false);
      return;
    }
    if (!agree) {
      setError('Необходимо принять условия оферты и политику конфиденциальности');
      setLoading(false);
      return;
    }

    try {
      const result = await api.register({
        email: regEmail.trim(),
        username: regUsername.trim(),
        password: regPassword,
        consent: agree,         // ✅ передаём согласие на сервер
      });

      const data = await api.login({ username: regUsername.trim(), password: regPassword });
      onLogin(data.access_token);
      onClose();
    } catch (err) {
      setError(err.message || 'Ошибка регистрации');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-auth" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{tab === 'login' ? '🔐 Вход' : '✨ Регистрация'}</h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <div className="import-method-toggle" style={{ marginBottom: '1rem' }}>
          <button className={`toggle-btn ${tab === 'login' ? 'active' : ''}`} onClick={() => setTab('login')}>
            Вход
          </button>
          <button className={`toggle-btn ${tab === 'register' ? 'active' : ''}`} onClick={() => setTab('register')}>
            Регистрация
          </button>
        </div>

        {error && <div className="alert alert-error" style={{ marginBottom: '1rem' }}><div>{error}</div></div>}

        {tab === 'login' ? (
          <form onSubmit={submitLogin}>
            <label className="form-label">Логин</label>
            <input className="form-input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin" required />
            <label className="form-label">Пароль</label>
            <input className="form-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
            <div className="modal-actions">
              <Button type="submit" disabled={loading} loading={loading}>Войти</Button>
            </div>
          </form>
        ) : (
          <form onSubmit={submitRegister}>
            <label className="form-label">Email</label>
            <input className="form-input" type="email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)} placeholder="you@mail.ru" required />
            <label className="form-label">Логин</label>
            <input className="form-input" value={regUsername} onChange={(e) => setRegUsername(e.target.value)} placeholder="seller123" required />
            <label className="form-label">Пароль</label>
            <input className="form-input" type="password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} placeholder="Минимум 6 символов" required />

            {/* ✅ Checkbox согласия */}
            <label className="bulk-check" style={{ margin: '0.75rem 0', fontWeight: 400, display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
              <input
                type="checkbox"
                checked={agree}
                onChange={(e) => setAgree(e.target.checked)}
                style={{ marginTop: '3px' }}
              />
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                Я принимаю{' '}
                <a href="#/terms" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-primary)' }}>условия оферты</a>
                {' '}и{' '}
                <a href="#/privacy" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-primary)' }}>политику конфиденциальности</a>
              </span>
            </label>

            <div className="modal-actions">
              <Button
                type="submit"
                disabled={loading || !agree}
                loading={loading}
              >
                Создать аккаунт
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default AuthModal;