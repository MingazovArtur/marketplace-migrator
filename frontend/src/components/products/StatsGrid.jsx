import React from 'react';

const StatsGrid = ({ stats }) => {
  const items = [
    { label: 'Всего товаров', value: stats?.total ?? 0, cls: '' },
    { label: 'Ожидают', value: stats?.pending ?? 0, cls: '' },
    { label: 'Успешно', value: stats?.success ?? 0, cls: 'success' },
    { label: 'Ошибки', value: stats?.error ?? 0, cls: 'error' },
  ];

  return (
    <div className="stats-grid">
      {items.map((it) => (
        <div key={it.label} className={`stat-card ${it.cls}`}>
          <div className="stat-label">{it.label.toUpperCase()}</div>
          <div className="stat-value">{Number(it.value).toLocaleString('ru-RU')}</div>
        </div>
      ))}
    </div>
  );
};

export default StatsGrid;