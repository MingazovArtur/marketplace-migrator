import React from 'react';
import Button from '../common/Button';
import ProfileMenu from '../profile/ProfileMenu';

const TopBar = ({ isAuthenticated, user, onOpenAuth, onLogout, onOpenHistory }) => (
  <header className="topbar">
    <div className="topbar-brand">
      <div className="topbar-logo">🔄</div>
      <span className="topbar-title">Marketplace Migrator</span>
    </div>

    <div className="topbar-actions">
      {isAuthenticated ? (
        <ProfileMenu user={user} onLogout={onLogout} onOpenHistory={onOpenHistory} />
      ) : (
        <>
          <Button variant="secondary" onClick={() => onOpenAuth('register')}>
            Регистрация
          </Button>
          <Button onClick={() => onOpenAuth('login')}>Войти</Button>
        </>
      )}
    </div>
  </header>
);

export default TopBar;