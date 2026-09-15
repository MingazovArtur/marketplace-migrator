import React from 'react';

const Alert = ({ message, onClose }) => {
  if (!message) return null;

  const isSuccess = message.includes('✅');
  const className = `alert ${isSuccess ? 'alert-success' : 'alert-error'}`;

  return (
    <div className={className}>
      <div>
        {message.split('\n').map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
      {onClose && (
        <button onClick={onClose} className="alert-close">✕</button>
      )}
    </div>
  );
};

export default Alert;