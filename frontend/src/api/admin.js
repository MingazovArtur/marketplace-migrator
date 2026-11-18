/* Admin (админ-панель: пользователи, статистика, журнал доступа).
 * Все методы требуют роль admin (бэкенд: get_current_admin_user). */

import { API_URL, doFetch, enc, getHeaders, safeError } from './client';

export const adminApi = {
  getUsers: async (search = '', skip = 0, limit = 25) => {
    const res = await doFetch(
      `${API_URL}/admin/users?search=${enc(search)}&skip=${enc(skip)}&limit=${enc(limit)}`,
      { headers: getHeaders() }
    );
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить пользователей'));
    return res.json();
  },

  updateUser: async (userId, payload) => {
    const res = await doFetch(`${API_URL}/admin/users/${enc(userId)}`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось обновить пользователя'));
    return res.json();
  },

  getStats: async () => {
    const res = await doFetch(`${API_URL}/admin/stats`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить статистику'));
    return res.json();
  },

  getAccessLogs: async (limit = 50) => {
    const res = await doFetch(`${API_URL}/admin/access-logs?limit=${enc(limit)}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить журнал доступа'));
    return res.json();
  },
};
