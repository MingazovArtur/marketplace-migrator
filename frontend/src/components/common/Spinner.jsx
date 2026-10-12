import React from 'react';

const Spinner = ({ size = 16, dark = false, className = '' }) => {
  return (
    <span
      className={`spinner ${dark ? 'spinner-dark' : ''} ${className}`}
      style={{ width: size, height: size }}
    />
  );
};

export default Spinner;
