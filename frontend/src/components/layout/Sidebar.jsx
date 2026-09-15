import React from 'react';
import {
  DashboardIcon,
  ProductsIcon,
  ImportIcon,
  MappingIcon,
  HistoryIcon,
  SettingsIcon,
  LogoutIcon,
  LogoIcon
} from '../icons/Icons';
import { useTheme } from '../../hooks/useTheme';

const Sidebar = ({ 
  currentView, 
  setCurrentView, 
  onLogout,
  userRole 
}) => {
  const { theme, toggleTheme } = useTheme();

  const menuItems = [
    { id: 'dashboard', label: 'Дашборд', icon: DashboardIcon },
    { id: 'products', label: 'Товары', icon: ProductsIcon },
    { id: 'import', label: 'Импорт', icon: ImportIcon },
    { id: 'mapping', label: 'Маппинг', icon: MappingIcon },
    { id: 'history', label: 'История', icon: HistoryIcon },
  ];

  if (userRole === 'admin') {
    menuItems.push({ id: 'settings', label: 'Настройки', icon: SettingsIcon });
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">
          <LogoIcon size={24} />
        </div>
        <div className="sidebar-logo-text">Migrator</div>
      </div>

      <nav className="sidebar-nav">
        {menuItems.map(item => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={`sidebar-item ${currentView === item.id ? 'active' : ''}`}
              onClick={() => setCurrentView(item.id)}
            >
              <span className="sidebar-item-icon">
                <Icon size={22} />
              </span>
              <span className="sidebar-item-text">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div className="theme-toggle" onClick={toggleTheme}>
          <span className="theme-toggle-label">
            {theme === 'dark' ? '🌙' : '☀️'} Тема
          </span>
          <div className="theme-switch" />
        </div>
        <button className="sidebar-item" onClick={onLogout}>
          <span className="sidebar-item-icon">
            <LogoutIcon size={22} />
          </span>
          <span className="sidebar-item-text">Выйти</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;