import React from 'react';
import Icon from '../icons';
import Button from '../common/Button';
import ProfileMenu from '../profile/ProfileMenu';

const HelpLink = () => (
  <a href="#/help" className="topbar-help-link" title="Гайд по переносу товаров и справка">
    <Icon name="help" size={18} />
    Помощь
  </a>
);

const TopBar = ({ isAuthenticated, user, onOpenAuth, onLogout, onOpenHistory }) => (
  <header className="topbar">
    <div className="topbar-brand">
      <span className="topbar-logo">
        <Icon name="logo" size={22} />
      </span>
      <span className="topbar-title">Marketplace Migrator</span>
    </div>

    <div className="topbar-actions">
      {isAuthenticated ? (
        <>
          <HelpLink />
          <ProfileMenu user={user} onLogout={onLogout} onOpenHistory={onOpenHistory} />
        </>
      ) : (
        <>
          <HelpLink />
          <Button variant="secondary" onClick={() => onOpenAuth('register')}>Регистрация</Button>
          <Button onClick={() => onOpenAuth('login')}>Войти</Button>
        </>
      )}
    </div>
  </header>
);

export default TopBar;