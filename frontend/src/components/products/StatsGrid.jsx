import React from 'react';
import AnimatedCounter from '../common/AnimatedCounter';

const StatsGrid = ({ stats }) => {
  const items = [
    { 
      label: 'Всего товаров', 
      value: stats.total || 0, 
      className: '',
      cardClass: ''
    },
    { 
      label: 'Ожидают', 
      value: stats.pending || 0, 
      className: 'text-warning',
      cardClass: 'warning'
    },
    { 
      label: 'Успешно', 
      value: stats.success || 0, 
      className: 'text-success',
      cardClass: 'success'
    },
    { 
      label: 'Ошибки', 
      value: stats.error || 0, 
      className: 'text-danger',
      cardClass: 'danger'
    }
  ];

  return (
    <div className="stats-grid">
      {items.map((item, index) => (
        <div key={index} className={`stat-card ${item.cardClass}`}>
          <div className="stat-label">{item.label}</div>
          <div className="stat-value" style={{ color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary') }}>
            <AnimatedCounter target={item.value} duration={1200} />
          </div>
        </div>
      ))}
    </div>
  );
};

export default StatsGrid;