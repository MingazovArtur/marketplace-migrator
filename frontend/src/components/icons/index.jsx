import React from 'react';

/*
  Единый реестр SVG-иконок бренда Marketplace Migrator.
  Стиль: толстые скруглённые штрихи, двухтонность:
    - основной контур  -> currentColor (адаптируется к теме);
    - акцентные детали -> var(--icon-accent) (голубой в тёмной, синий в светлой).

  Использование в любом компоненте:
    import Icon from '../icons';
    <Icon name="import" size={16} />

  Доступные имена:
    logo, dashboard, products, import, export, mapping, history, migrate,
    photo, tag, variants, report, edit, refresh, search, sun, moon, logout,
    star, trash, plus, close, check, alert, chevron-left, chevron-right,
    template, key, file, info
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
      <g stroke={A}><path d="M12 20V5" /></g>
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
      <g stroke={A}><path d="M12 7v5l4 2" /></g>
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
      <g stroke={A}><circle cx="7.5" cy="7.5" r="1.2" fill={A} stroke="none" /></g>
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
      <g stroke={A}><path d="m15 5 4 4" /></g>
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
  search: (
    <>
      <g stroke="currentColor"><circle cx="11" cy="11" r="7" /></g>
      <g stroke={A}><path d="m21 21-4.3-4.3" /></g>
    </>
  ),
  sun: (
    <>
      <g stroke="currentColor"><circle cx="12" cy="12" r="4" /></g>
      <g stroke={A}>
        <path d="M12 2v2" /><path d="M12 20v2" />
        <path d="m4.9 4.9 1.4 1.4" /><path d="m17.7 17.7 1.4 1.4" />
        <path d="M2 12h2" /><path d="M20 12h2" />
        <path d="m4.9 19.1 1.4-1.4" /><path d="m17.7 6.3 1.4-1.4" />
      </g>
    </>
  ),
  moon: (
    <>
      <g stroke="currentColor">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
      </g>
      <g stroke={A}><circle cx="18" cy="5" r="0.9" fill={A} stroke="none" /></g>
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
    <g stroke="currentColor"><path d="M20 6 9 17l-5-5" /></g>
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
    <g stroke="currentColor"><path d="m15 18-6-6 6-6" /></g>
  ),
  'chevron-right': (
    <g stroke="currentColor"><path d="m9 18 6-6-6-6" /></g>
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
      <g stroke={A}><path d="M14 2v6h6" /></g>
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
 * <Icon name="import" size={16} /> — размер в px, цвет наследуется (currentColor),
 * акцент берётся из CSS-переменной --icon-accent (меняется по теме).
 */
export const Icon = ({ name, size = 20, className = '' }) => {
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

/* Удобные алиасы, если где-то встретятся старые имена */
export const DownloadIcon = (p) => <Icon name="import" {...p} />;
export const UploadIcon = (p) => <Icon name="export" {...p} />;
export const MigrateIcon = (p) => <Icon name="migrate" {...p} />;
export const PhotoIcon = (p) => <Icon name="photo" {...p} />;
export const TagIcon = (p) => <Icon name="tag" {...p} />;
export const VariantsIcon = (p) => <Icon name="variants" {...p} />;
export const ReportIcon = (p) => <Icon name="report" {...p} />;
export const EditIcon = (p) => <Icon name="edit" {...p} />;
export const RefreshIcon = (p) => <Icon name="refresh" {...p} />;
export const SearchIcon = (p) => <Icon name="search" {...p} />;
export const LogoIcon = (p) => <Icon name="logo" {...p} />;
export const DashboardIcon = (p) => <Icon name="dashboard" {...p} />;
export const ProductsIcon = (p) => <Icon name="products" {...p} />;
export const ImportIcon = (p) => <Icon name="import" {...p} />;
export const ExportIcon = (p) => <Icon name="export" {...p} />;
export const MappingIcon = (p) => <Icon name="mapping" {...p} />;
export const HistoryIcon = (p) => <Icon name="history" {...p} />;
export const SunIcon = (p) => <Icon name="sun" {...p} />;
export const MoonIcon = (p) => <Icon name="moon" {...p} />;
export const LogoutIcon = (p) => <Icon name="logout" {...p} />;
export const CloseIcon = (p) => <Icon name="close" {...p} />;
export const StarIcon = (p) => <Icon name="star" {...p} />;
export const TrashIcon = (p) => <Icon name="trash" {...p} />;
export const PlusIcon = (p) => <Icon name="plus" {...p} />;
export const CheckIcon = (p) => <Icon name="check" {...p} />;
export const AlertIcon = (p) => <Icon name="alert" {...p} />;
export const TemplateIcon = (p) => <Icon name="template" {...p} />;
export const KeyIcon = (p) => <Icon name="key" {...p} />;
export const FileIcon = (p) => <Icon name="file" {...p} />;
export const InfoIcon = (p) => <Icon name="info" {...p} />;

export default Icon;