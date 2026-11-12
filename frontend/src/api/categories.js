/* Площадки и категории: справочники, маппинг категорий
 * (Р5: вынесено из api.js — секция «Platforms & categories»). */

import { API_URL, doFetch, enc, getHeaders, safeError } from './client';

export const categoriesApi = {
  getPlatforms: async () => {
    const res = await doFetch(`${API_URL}/platforms`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить платформы'));
    return res.json();
  },

  getCategories: async (platform) => {
    const res = await doFetch(`${API_URL}/categories/${enc(platform)}`, { headers: getHeaders() });
    if (res.status === 404) return [];
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить категории'));
    return res.json();
  },

  refreshCategories: async (platform, apiKey) => {
    const q = new URLSearchParams({ api_key: apiKey || '' });
    const res = await doFetch(`${API_URL}/categories/${enc(platform)}/refresh?${q.toString()}`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ api_key: apiKey || '' }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка обновления категорий из API'));
    return res.json();
  },

  getCategoryMapping: async (sourcePlatform, targetPlatform) => {
    const q = new URLSearchParams({
      source_platform: sourcePlatform || '',
      target_platform: targetPlatform || '',
    });
    const res = await doFetch(`${API_URL}/category-mapping?${q.toString()}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить маппинг категорий'));
    return res.json();
  },

  saveCategoryMapping: async (
    sourcePlatform,
    sourceCategoryId,
    targetPlatform,
    targetCategoryId
  ) => {
    const q = new URLSearchParams({
      source_platform: sourcePlatform,
      source_category_id: String(sourceCategoryId),
      target_platform: targetPlatform,
      target_category_id: String(targetCategoryId),
    });
    const res = await doFetch(`${API_URL}/category-mapping?${q.toString()}`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения маппинга'));
    return res.json();
  },

  deleteCategoryMapping: async (mappingId) => {
    const res = await doFetch(`${API_URL}/category-mapping/${enc(mappingId)}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка удаления маппинга'));
    return res.json();
  },
};
