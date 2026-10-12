import React, { useState, useEffect, useCallback } from 'react';

const Alert = ({ message, onClose, autoClose = false }) => {
  const [closing, setClosing] = useState(false);

  // ✅ 1. Объявляем функцию ДО использования в useEffect
  const handleClose = useCallback(() => {
    setClosing(true);
    setTimeout(() => {
      onClose?.();
    }, 300);
  }, [onClose]);

  // ✅ 2. Теперь handleClose можно безопасно вызывать здесь
  useEffect(() => {
    if (autoClose && message) {
      const timer = setTimeout(() => {
        handleClose();
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [message, autoClose, handleClose]);

  if (!message) return null;

  const isSuccess = message.includes('✅');
  const className = `alert ${isSuccess ? 'alert-success' : 'alert-error'} ${closing ? 'closing' : ''}`;

  return (
    <div className={className}>
      <div>
        {message.split('\n').map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
      {onClose && (
        <button 
          type="button" 
          onClick={handleClose} 
          className="alert-close" 
          title="Закрыть"
        >
          ✕
        </button>
      )}
    </div>
  );
};

export default Alert;