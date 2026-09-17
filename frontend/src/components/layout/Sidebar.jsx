import React from 'react';
import { DashboardIcon, ProductsIcon, ImportIcon, MappingIcon, HistoryIcon } from '../icons/Icons';

const NAV = [
  { id: 'dashboard', label: 'Дашборд', Icon: DashboardIcon },
  { id: 'products', label: 'Товары', Icon: ProductsIcon },
  { id: 'import', label: 'Импорт', Icon: ImportIcon },
  { id: 'mapping', label: 'Маппинг', Icon: MappingIcon },
  { id: 'history', label: 'История', Icon: HistoryIcon },
];

const Sidebar = ({ currentView, setCurrentView, theme, setTheme }) => (
  <aside className="sidebar">
    <nav className="sidebar-nav">
      {NAV.map(({ id, label, Icon }) => (
        <button
          key={id}
          className={`sidebar-item ${currentView === id ? 'active' : ''}`}
          onClick={() => setCurrentView(id)}
        >
          <Icon size={18} />
          <span>{label}</span>
        </button>
      ))}
    </nav>

    <div className="sidebar-footer">
      <button
        type="button"
        className={`theme-toggle ${theme === 'light' ? 'on' : ''}`}
        onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
        title="Переключить тему"
      >
        <span className="theme-toggle-icon" aria-hidden="true">
          {theme === 'light' ? '☀️' : '🌙'}
        </span>
        <span className="theme-toggle-text">
          {theme === 'light' ? 'Светлая тема' : 'Тёмная тема'}
        </span>
        <span className="theme-toggle-switch" aria-hidden="true">
          <span className="theme-toggle-knob" />
        </span>
      </button>
    </div>
  </aside>
);

export default Sidebar;