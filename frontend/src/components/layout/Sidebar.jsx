import React from 'react';
import Icon from '../icons';

const NAV = [
  { id: 'dashboard', label: 'Дашборд', icon: 'dashboard' },
  { id: 'products', label: 'Товары', icon: 'products' },
  { id: 'import', label: 'Импорт', icon: 'import' },
  { id: 'mapping', label: 'Маппинг', icon: 'mapping' },
  { id: 'specs', label: 'Спецификации', icon: 'layers' },
  { id: 'templates', label: 'Шаблоны', icon: 'template' }, // ✅ управление эталонами Ozon
  { id: 'history', label: 'История', icon: 'history' },
];

const Sidebar = ({ currentView, setCurrentView, theme, setTheme }) => (
  <aside className="sidebar">
    <nav className="sidebar-nav">
      {NAV.map(({ id, label, icon }) => (
        <button
          key={id}
          className={`sidebar-item ${currentView === id ? 'active' : ''}`}
          onClick={() => setCurrentView(id)}
        >
          <Icon name={icon} size={20} />
          <span className="sidebar-item-text">{label}</span>
        </button>
      ))}
    </nav>

    <div className="sidebar-footer">
      <button
        type="button"
        className={`theme-toggle ${theme === 'light' ? 'on' : ''}`}
        onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
      >
        <Icon name={theme === 'light' ? 'sun' : 'moon'} size={18} />
        <span className="theme-toggle-text">
          {theme === 'light' ? 'Светлая тема' : 'Тёмная тема'}
        </span>
        <span className="theme-toggle-switch">
          <span className="theme-toggle-knob" />
        </span>
      </button>
    </div>
  </aside>
);

export default Sidebar;
