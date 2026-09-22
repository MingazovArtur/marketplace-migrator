import React from 'react';

const Badge = ({ status, label }) => {
  const styles = {
    pending: 'badge-pending',
    success: 'badge-success',
    error: 'badge-error',
    processing: 'badge-processing'
  };

  const labels = {
    pending: 'Ожидает',
    success: 'Успешно',
    error: 'Ошибка',
    processing: 'В процессе'
  };

  return (
    <span className={`badge ${styles[status]}`}>
      {label || labels[status]}
    </span>
  );
};

export default Badge;