/* Дефолты экспорта: глобальные/по категориям, счётчик пропусков, дозаполнение
 * (Р5: вынесено из api.js — секция «Дефолты экспорта»). */

import { API_URL, doFetch, enc, getAuthHeaders, getHeaders, safeError } from './client';

export const defaultsApi = {
  getDefaults: async () => {
    const res = await doFetch(`${API_URL}/defaults`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить дефолты'));
    return res.json();
  },

  saveDefaults: async (payload) => {
    const res = await doFetch(`${API_URL}/defaults`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сохранить дефолты'));
    return res.json();
  },

  deleteCategoryDefaults: async (categoryName) => {
    const res = await doFetch(`${API_URL}/defaults/category?category_name=${enc(categoryName)}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось удалить дефолты категории'));
    return res.json();
  },

  getGaps: async (status = 'all') => {
    const res = await doFetch(`${API_URL}/defaults/gaps?status=${enc(status)}`, {
      headers: getHeaders(),
    });
    if (!res.ok) return { total: 0, gaps: {} };
    return res.json();
  },

  applyDefaults: async (modeOrPayload = 'all') => {
    const body = modeOrPayload && typeof modeOrPayload === 'object' ? modeOrPayload : null;
    const q = !body && modeOrPayload ? `?status=${enc(modeOrPayload)}` : '';
    const res = await doFetch(`${API_URL}/products/apply-defaults${q}`, {
      method: 'POST',
      headers: body ? getHeaders() : getAuthHeaders(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось заполнить пропуски'));
    return res.json();
  },
};
