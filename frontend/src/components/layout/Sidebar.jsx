import React from 'react';
import { NavLink } from 'react-router-dom';
import Icon from '../icons';

/* Round 7: навигация переехала на маршруты React Router — активный пункт
 * определяется адресом (NavLink), а не пропом currentView из App.
 * Пути 1:1 повторяют старые id вкладок, так что сохранение последней
 * вкладки (localStorage 'marketplace_active_view') остаётся совместимым. */
const NAV = [
  { to: '/dashboard', label: 'Дашборд', icon: 'dashboard' },
  { to: '/products', label: 'Товары', icon: 'products' },
  { to: '/import', label: 'Импорт', icon: 'import' },
  { to: '/mapping', label: 'Маппинг', icon: 'mapping' },
  { to: '/specs', label: 'Спецификации', icon: 'layers' },
  { to: '/templates', label: 'Шаблоны', icon: 'template' }, // ✅ управление эталонами Ozon
  { to: '/history', label: 'История', icon: 'history' },
];

// Мониторинг загрузок спеков (очередь Celery + прогресс) — только для админа,
// вставляется сразу после «Спецификаций»
const ADMIN_NAV_ITEM = { to: '/specs-monitor', label: 'Мониторинг спеков', icon: 'report' };

const Sidebar = ({ theme, setTheme, isAdmin = false }) => {
  const items = isAdmin ? [...NAV.slice(0, 5), ADMIN_NAV_ITEM, ...NAV.slice(5)] : NAV;

  return (
    <aside className="sidebar">
      <nav className="sidebar-nav">
        {items.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}
            data-onboarding={to === '/specs' ? 'specs-nav' : undefined}
          >
            <Icon name={icon} size={20} />
            <span className="sidebar-item-text">{label}</span>
          </NavLink>
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
};

export default Sidebar;
