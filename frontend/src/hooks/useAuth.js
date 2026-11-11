import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

/**
 * Аутентификация на httpOnly-cookie (v3):
 *  - токен больше НЕ хранится в localStorage (JS не может его прочитать — защита от XSS);
 *  - логин ставит куки access_token (httpOnly) + csrf_token (читаемая) на сервере;
 *  - состояние = результат GET /auth/me (200 -> вошли, 401 -> нет);
 *  - logout — POST /auth/logout, сервер чистит обе куки.
 */
export const useAuth = () => {
  const [authChecked, setAuthChecked] = useState(false);
  const [user, setUser] = useState(null);

  const loadUser = useCallback(async () => {
    try {
      const me = await api.getMe();
      setUser(me);
      return true;
    } catch {
      setUser(null);
      return false;
    } finally {
      setAuthChecked(true);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  // Куки ставит сервер в ответе POST /auth/login; аргумент (токен) игнорируем —
  // для совместимости со старыми вызовами onLogin(data.access_token)
  const handleLogin = useCallback(async () => {
    await loadUser();
  }, [loadUser]);

  const handleLogout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  return {
    authChecked,
    isAuthenticated: !!user,
    user,
    handleLogin,
    handleLogout,
    reloadUser: loadUser,
  };
};
