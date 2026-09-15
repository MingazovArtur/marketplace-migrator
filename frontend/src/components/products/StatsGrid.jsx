import React from 'react';

const StatsGrid = ({ stats }) => {
  const statItems = [
    { label: 'Всего товаров', value: stats.total, color: 'var(--text-primary)' },
    { label: 'Ожидают', value: stats.pending, color: '#f59e0b' },
    { label: 'Успешно', value: stats.success, color: '#10b981' },
    { label: 'Ошибки', value: stats.error, color: '#ef4444' }
  ];

  return (
    <div className="stats-grid">
      {statItems.map((item, index) => (
        <div key={index} className="stat-card">
          <div className="stat-label">{item.label}</div>
          <div className="stat-value" style={{ color: item.color }}>
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
};

export default StatsGrid;