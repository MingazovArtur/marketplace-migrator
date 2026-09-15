import React, { useState, useEffect } from 'react';

const Alert = ({ message, onClose, autoClose = false }) => {
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    if (autoClose && message) {
      const timer = setTimeout(() => {
        handleClose();
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [message, autoClose]);

  const handleClose = () => {
    setClosing(true);
    setTimeout(() => {
      onClose?.();
    }, 300);
  };

  if (!message) return null;

  const isSuccess = message.includes('✅');
  const className = `alert ${isSuccess ? 'alert-success' : 'alert-error'} ${closing ? 'closing' : ''}`;

  return (
    <div className={className}>
      <div>{message}</div>
      {onClose && (
        <button onClick={handleClose} className="alert-close"></button>
      )}
    </div>
  );
};

export default Alert;