import React from 'react';

/*
  Единый реестр SVG-иконок бренда Marketplace Migrator.
  Стиль: толстые скруглённые штрихи, двухтонность:
    - основной контур  -> currentColor (адаптируется к теме);
    - акцентные детали -> var(--icon-accent) (голубой в тёмной, синий в светлой).

  Использование:
    import Icon from '../icons';
    <Icon name="import" size={16} />
*/

const A = 'var(--icon-accent)';

const ICONS = {
  /* ---------- Логотип ---------- */
  logo: (
    <>
      <g stroke="currentColor">
        <path d="M12 2.5 20.5 7v10L12 21.5 3.5 17V7Z" />
      </g>
      <g stroke={A}>
        <path d="m3.5 7 8.5 5 8.5-5" />
        <path d="M12 12v9.5" />
      </g>
    </>
  ),

  /* ---------- Навигация ---------- */
  dashboard: (
    <>
      <g stroke="currentColor">
        <path d="M5 20v-7" />
        <path d="M19 20V9" />
        <path d="M3 21h18" />
      </g>
      <g stroke={A}>
        <path d="M12 20V5" />
      </g>
    </>
  ),
  products: (
    <>
      <g stroke="currentColor">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
      </g>
      <g stroke={A}>
        <path d="m3.3 7 8.7 5 8.7-5" />
        <path d="M12 12v10" />
      </g>
    </>
  ),
  import: (
    <>
      <g stroke="currentColor">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      </g>
      <g stroke={A}>
        <path d="M12 3v12" />
        <path d="m7 10 5 5 5-5" />
      </g>
    </>
  ),
  export: (
    <>
      <g stroke="currentColor">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      </g>
      <g stroke={A}>
        <path d="M12 15V3" />
        <path d="m7 8 5-5 5 5" />
      </g>
    </>
  ),
  mapping: (
    <>
      <g stroke="currentColor">
        <circle cx="5" cy="12" r="2.5" />
        <circle cx="19" cy="12" r="2.5" />
      </g>
      <g stroke={A}>
        <path d="M8 12h8" />
        <path d="m13 9 3 3-3 3" />
      </g>
    </>
  ),
  history: (
    <>
      <g stroke="currentColor">
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
        <path d="M3 3v5h5" />
      </g>
      <g stroke={A}>
        <path d="M12 7v5l4 2" />
      </g>
    </>
  ),

  /* ---------- Действия с товарами ---------- */
  migrate: (
    <>
      <g stroke="currentColor">
        <rect x="3" y="7" width="8" height="8" rx="2" fill="currentColor" stroke="none" />
        <rect x="13.5" y="7" width="8" height="8" rx="2" />
      </g>
      <g stroke={A}>
        <path d="M10.5 11h5" />
        <path d="m13.5 8.5 2.5 2.5-2.5 2.5" />
      </g>
    </>
  ),
  photo: (
    <>
      <g stroke="currentColor">
        <rect x="3" y="3" width="18" height="18" rx="2" />
      </g>
      <g stroke={A}>
        <circle cx="8.5" cy="8.5" r="1.5" fill={A} stroke="none" />
        <path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21" />
      </g>
    </>
  ),
  tag: (
    <>
      <g stroke="currentColor">
        <path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" />
      </g>
      <g stroke={A}>
        <circle cx="7.5" cy="7.5" r="1.2" fill={A} stroke="none" />
      </g>
    </>
  ),
  box: (
    <>
      <g stroke="currentColor">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
      </g>
      <g stroke={A}>
        <path d="m3.27 6.96 8.73 5.05 8.73-5.05" />
        <path d="M12 22.08V12" />
      </g>
    </>
  ),
  trash: (
    <>
      <g stroke="currentColor">
        <path d="M3 6h18" />
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
        <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      </g>
      <g stroke={A}>
        <path d="M10 11v6" />
        <path d="M14 11v6" />
      </g>
    </>
  ),
  variants: (
    <>
      <g stroke="currentColor">
        <rect x="9" y="2.5" width="6" height="6" rx="1.5" />
        <rect x="3.5" y="15.5" width="6" height="6" rx="1.5" />
        <rect x="14.5" y="15.5" width="6" height="6" rx="1.5" />
      </g>
      <g stroke={A}>
        <path d="M12 8.5v3" />
        <path d="m12 11.5-5 4" />
        <path d="m12 11.5 5 4" />
      </g>
    </>
  ),
  report: (
    <>
      <g stroke="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
        <path d="M14 2v6h6" />
      </g>
      <g stroke={A}>
        <path d="M8 17v-3" />
        <path d="M12 17v-6" />
        <path d="M16 17v-2" />
      </g>
    </>
  ),
  edit: (
    <>
      <g stroke="currentColor">
        <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      </g>
      <g stroke={A}>
        <path d="m15 5 4 4" />
      </g>
    </>
  ),
  refresh: (
    <>
      <g stroke="currentColor">
        <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
        <path d="M3 3v5h5" />
      </g>
      <g stroke={A}>
        <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
        <path d="M21 21v-5h-5" />
      </g>
    </>
  ),

  /* ---------- Служебные ---------- */
  settings: (
    <>
      <g stroke="currentColor">
        <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      </g>
      <g stroke={A}>
        <circle cx="12" cy="12" r="3" />
      </g>
    </>
  ),
  search: (
    <>
      <g stroke="currentColor">
        <circle cx="11" cy="11" r="7" />
      </g>
      <g stroke={A}>
        <path d="m21 21-4.3-4.3" />
      </g>
    </>
  ),
  sun: (
    <>
      <g stroke="currentColor">
        <circle cx="12" cy="12" r="4" />
      </g>
      <g stroke={A}>
        <path d="M12 2v2" />
        <path d="M12 20v2" />
        <path d="m4.9 4.9 1.4 1.4" />
        <path d="m17.7 17.7 1.4 1.4" />
        <path d="M2 12h2" />
        <path d="M20 12h2" />
        <path d="m4.9 19.1 1.4-1.4" />
        <path d="m17.7 6.3 1.4-1.4" />
      </g>
    </>
  ),
  moon: (
    <>
      <g stroke="currentColor">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
      </g>
      <g stroke={A}>
        <circle cx="18" cy="5" r="0.9" fill={A} stroke="none" />
      </g>
    </>
  ),
  logout: (
    <>
      <g stroke="currentColor">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      </g>
      <g stroke={A}>
        <path d="m16 17 5-5-5-5" />
        <path d="M21 12H9" />
      </g>
    </>
  ),
  star: (
    <g stroke="currentColor">
      <path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.5-2.9-5.5 2.9 1-6.1L3.2 9.5l6.1-.9Z" />
    </g>
  ),
  plus: (
    <g stroke="currentColor">
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </g>
  ),
  close: (
    <g stroke="currentColor">
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </g>
  ),
  check: (
    <g stroke="currentColor">
      <path d="M20 6 9 17l-5-5" />
    </g>
  ),
  alert: (
    <>
      <g stroke="currentColor">
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 2 21h20a2 2 0 0 0 1.73-3Z" />
      </g>
      <g stroke={A}>
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </g>
    </>
  ),
  info: (
    <>
      <g stroke="currentColor">
        <circle cx="12" cy="12" r="9" />
      </g>
      <g stroke={A}>
        <path d="M12 16v-5" />
        <path d="M12 8h.01" />
      </g>
    </>
  ),
  'chevron-left': (
    <g stroke="currentColor">
      <path d="m15 18-6-6 6-6" />
    </g>
  ),
  'chevron-right': (
    <g stroke="currentColor">
      <path d="m9 18 6-6-6-6" />
    </g>
  ),

  /* ---------- Разное ---------- */
  book: (
    <g stroke="currentColor">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </g>
  ),
  warning: (
    <>
      <g stroke="currentColor">
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      </g>
      <g stroke={A}>
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </g>
    </>
  ),
  layers: (
    <>
      <g stroke="currentColor">
        <polygon points="12 2 2 7 12 12 22 7 12 2" />
      </g>
      <g stroke={A}>
        <polyline points="2 17 12 22 22 17" />
        <polyline points="2 12 12 17 22 12" />
      </g>
    </>
  ),
  help: (
    <>
      <g stroke="currentColor">
        <circle cx="12" cy="12" r="10" />
      </g>
      <g stroke={A}>
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </g>
    </>
  ),
  save: (
    <>
      <g stroke="currentColor">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
      </g>
      <g stroke={A}>
        <polyline points="17 21 17 13 7 13 7 21" />
        <polyline points="7 3 7 8 15 8" />
      </g>
    </>
  ),
  lock: (
    <>
      <g stroke="currentColor">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      </g>
      <g stroke={A}>
        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
      </g>
    </>
  ),
  'user-plus': (
    <>
      <g stroke="currentColor">
        <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="8.5" cy="7" r="4" />
      </g>
      <g stroke={A}>
        <line x1="20" y1="8" x2="20" y2="14" />
        <line x1="23" y1="11" x2="17" y2="11" />
      </g>
    </>
  ),

  /* ---------- Документы ---------- */
  template: (
    <>
      <g stroke="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
        <path d="M14 2v6h6" />
      </g>
      <g stroke={A}>
        <path d="M8 13h8" />
        <path d="M8 17h5" />
      </g>
    </>
  ),
  file: (
    <>
      <g stroke="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      </g>
      <g stroke={A}>
        <path d="M14 2v6h6" />
      </g>
    </>
  ),
  key: (
    <>
      <g stroke="currentColor">
        <circle cx="7.5" cy="15.5" r="4.5" />
      </g>
      <g stroke={A}>
        <path d="m10.7 12.3 8.3-8.3" />
        <path d="m15 8 3 3" />
        <path d="m18 5 2 2" />
      </g>
    </>
  ),
};

/**
 * Единая иконка набора.
 */
const Icon = ({ name, size = 20, className = '' }) => {
  const body = ICONS[name];
  if (!body) return null;
  return (
    <svg
      className={`app-icon ${className}`.trim()}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      strokeWidth="2.1"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {body}
    </svg>
  );
};

export default Icon;