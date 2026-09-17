import React, { useState, useEffect, useRef } from 'react';
import { api } from '../../api';

const STATUS_CLS = { success: 'badge-success', partial: 'badge-pending', error: 'badge-error' };

const ProfileMenu = ({ user, onLogout, onOpenHistory }) => {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  useEffect(() => {
    if (open) {
      api.getHistory({ limit: 5 })
        .then((d) => setHistory(d.history || []))
        .catch(() => setHistory([]));
    }
  }, [open]);

  const initials = (user?.username || '??').slice(0, 2).toUpperCase();

  return (
    <div className="profile-menu" ref={ref}>
      <button className="profile-btn" onClick={() => setOpen((o) => !o)}>
        <span className="profile-avatar">{initials}</span>
        <span className="profile-name">{user?.username || 'Профиль'}</span>
        <span className="profile-caret">▾</span>
      </button>

      {open && (
        <div className="profile-dropdown">
          <div className="profile-dd-head">
            <div className="profile-avatar big">{initials}</div>
            <div>
              <div className="profile-dd-name">{user?.username}</div>
              <div className="profile-dd-email">{user?.email}</div>
            </div>
          </div>

          <div className="profile-dd-section">
            <div className="profile-dd-title">Последние операции</div>
            {history.length === 0 ? (
              <div className="profile-dd-empty">Пока нет операций</div>
            ) : (
              history.map((h) => (
                <div key={h.id} className="profile-dd-item">
                  <span className="profile-dd-desc" title={h.description}>{h.description}</span>
                  <span className={`badge ${STATUS_CLS[h.status] || 'badge-error'}`}>
                    {h.status === 'success' ? '✓' : h.status === 'partial' ? '!' : '✕'}
                  </span>
                </div>
              ))
            )}
          </div>

          <div className="profile-dd-actions">
            <button className="profile-dd-link" onClick={() => { setOpen(false); onOpenHistory(); }}>
              📜 Вся история
            </button>
            <button className="profile-dd-link danger" onClick={onLogout}>
              🚪 Выйти
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProfileMenu;