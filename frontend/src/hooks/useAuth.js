import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

export const useAuth = () => {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [user, setUser] = useState(null);

  const loadUser = useCallback(async () => {
    try {
      const me = await api.getMe();
      setUser(me);
    } catch {
      localStorage.removeItem('token');
      setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    if (token) loadUser();
    else setUser(null);
  }, [token, loadUser]);

  const handleLogin = useCallback((newToken) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
  }, []);

  const handleLogout = useCallback(() => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  }, []);

  return { token, isAuthenticated: !!token, user, handleLogin, handleLogout };
};
