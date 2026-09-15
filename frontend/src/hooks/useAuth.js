import { useState, useCallback } from 'react';
import { api } from '../api';

export const useAuth = () => {
  const [token, setToken] = useState(localStorage.getItem('token'));

  const handleLogin = useCallback((newToken) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
  }, []);

  const handleLogout = useCallback(() => {
    api.logout();
    setToken(null);
  }, []);

  return {
    token,
    isAuthenticated: !!token,
    handleLogin,
    handleLogout,
    setToken
  };
};