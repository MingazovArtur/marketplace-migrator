import React, { useState, useEffect, useRef } from 'react';
import Icon from '../icons';
import { api } from '../../api';

const STATUS_CLS = {
  success: 'badge-success',
  partial: 'badge-pending',
  error: 'badge-error',
};

const STATUS_SIGN = {
  success: '✓',
  partial: '!',
  error: '✕',
};

const ProfileMenu = ({ user, onLogout, onOpenHistory }) => {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const ref = useRef(null);

  // Закрытие по клику вне меню
  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  // Подгрузка последних операций при открытии
  useEffect(() => {
    if (open) {
      api
        .getHistory({ limit: 5 })
        .then((d) => setHistory(d.history || []))
        .catch(() => setHistory([]));
    }
  }, [open]);

  const initials = (user?.username || '??').slice(0, 2).toUpperCase();

  return (
    <div className="profile-menu" ref={ref}>
      <button
        type="button"
        className="profile-btn"
        onClick={() => setOpen((o) => !o)}
        title="Профиль"
      >
        <span className="profile-avatar">{initials}</span>
        <span className="profile-name">{user?.username}</span>
        <span className="profile-caret">▾</span>
      </button>

      {open && (
        <div className="profile-dropdown">
          {/* Шапка профиля */}
          <div className="profile-dd-head">
            <div className="profile-avatar big">{initials}</div>
            <div>
              <div className="profile-dd-name">{user?.username}</div>
              <div className="profile-dd-email">{user?.email}</div>
            </div>
          </div>

          {/* Последние операции */}
          <div className="profile-dd-section">
            <div className="profile-dd-title">Последние операции</div>
            {history.length === 0 ? (
              <div className="profile-dd-empty">Пока нет операций</div>
            ) : (
              history.map((h) => (
                <div key={h.id} className="profile-dd-item">
                  <span className="profile-dd-desc" title={h.description}>
                    {h.description}
                  </span>
                  <span className={`badge ${STATUS_CLS[h.status] || 'badge-error'}`}>
                    {STATUS_SIGN[h.status] || '✕'}
                  </span>
                </div>
              ))
            )}
          </div>

          {/* Действия */}
          <div className="profile-dd-actions">
            <button
              type="button"
              className="profile-dd-link"
              onClick={() => {
                setOpen(false);
                onOpenHistory();
              }}
            >
              <Icon name="history" size={16} /> Вся история
            </button>
            <button type="button" className="profile-dd-link danger" onClick={onLogout}>
              <Icon name="logout" size={16} /> Выйти
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProfileMenu;
