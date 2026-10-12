import React from 'react';
import Spinner from './Spinner';

const Button = ({
  children,
  variant = 'primary',
  disabled = false,
  loading = false,
  onClick,
  className = '',
  type = 'button',
  ...props
}) => {
  const variantClasses = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    outline: 'btn-outline',
  };

  const isLoading = loading || disabled;

  return (
    <button
      type={type}
      className={`btn ${variantClasses[variant]} ${isLoading ? 'btn-loading' : ''} ${className}`}
      disabled={isLoading}
      onClick={onClick}
      {...props}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
};

export default Button;
