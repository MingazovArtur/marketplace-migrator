import React from 'react';

const Modal = ({ isOpen, onClose, title, children, size = 'md', showCloseButton = true }) => {
  if (!isOpen) return null;

  const sizeClasses = {
    sm: 'modal-small',
    md: 'modal',
    lg: 'modal-preview',
    xl: 'modal-batch',
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className={`modal ${sizeClasses[size]}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          {showCloseButton && (
            <button className="close-btn" onClick={onClose}>
              ✕
            </button>
          )}
        </div>
        {children}
      </div>
    </div>
  );
};

export default Modal;
