/* Статистика и история операций (Р5: вынесено из api.js — секция «Stats / History»). */

import { API_URL, doFetch, enc, getHeaders, safeError } from './client';

export const statsApi = {
  getStats: async () => {
    const res = await doFetch(`${API_URL}/stats`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить статистику'));
    return res.json();
  },

  getDashboardStats: async (days = 7) => {
    const res = await doFetch(`${API_URL}/stats/dashboard?days=${enc(days)}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить дашборд статистики'));
    return res.json();
  },

  getHistory: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.operation) q.append('operation', params.operation);
    if (params.limit) q.append('limit', params.limit);
    const qs = q.toString();
    const res = await doFetch(`${API_URL}/history${qs ? '?' + qs : ''}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить историю'));
    return res.json();
  },
};
