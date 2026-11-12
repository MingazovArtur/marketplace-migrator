/* Auth + Email (Р5: вынесено из api.js, секции «Auth» и «Email»). */

import { API_URL, doFetch, getHeaders, safeError } from './client';

export const authApi = {
  login: async (credentials) => {
    const res = await doFetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка входа'));
    return res.json();
  },

  register: async (payload) => {
    const res = await doFetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка регистрации'));
    return res.json();
  },

  /* ✅ v5: настройки уведомлений (письмо о завершении пакетной миграции) */
  getNotifications: async () => {
    const res = await doFetch(`${API_URL}/auth/notifications`, { headers: getHeaders() });
    if (!res.ok)
      throw new Error(await safeError(res, 'Не удалось загрузить настройки уведомлений'));
    return res.json();
  },

  updateNotifications: async (payload) => {
    const res = await doFetch(`${API_URL}/auth/notifications`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok)
      throw new Error(await safeError(res, 'Не удалось сохранить настройки уведомлений'));
    return res.json();
  },

  logout: async () => {
    // Куки чистит backend (Set-Cookie с истечением); CSRF-заголовок обязателен
    try {
      await doFetch(`${API_URL}/auth/logout`, { method: 'POST', headers: getHeaders() });
    } catch {
      /* кука всё равно истечёт на сервере; локально чистить нечего */
    }
  },

  getCurrentUser: async () => {
    const res = await doFetch(`${API_URL}/auth/me`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось получить профиль'));
    return res.json();
  },

  getMe: async () => {
    const res = await doFetch(`${API_URL}/auth/me`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось получить профиль'));
    return res.json();
  },

  verifyEmail: async (token) => {
    const res = await doFetch(`${API_URL}/auth/verify-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось подтвердить email'));
    return res.json();
  },

  resendVerification: async () => {
    const res = await doFetch(`${API_URL}/auth/resend-verification`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось отправить письмо'));
    return res.json();
  },

  forgotPassword: async (email) => {
    const res = await doFetch(`${API_URL}/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка запроса сброса'));
    return res.json();
  },

  resetPassword: async (token, newPassword) => {
    const res = await doFetch(`${API_URL}/auth/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сбросить пароль'));
    return res.json();
  },
};
