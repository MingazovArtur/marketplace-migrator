/* Спецификации категорий: чтение/удаление/фоновая загрузка, мониторинг (админ)
 * (Р5: вынесено из api.js — секция «Спецификации категорий»).
 *
 * Round 8: прогресс загрузки и мониторинг — SSE-потоки (streamSpecsRefresh,
 * streamAdminSpecsTasks); старые polling-эндпоинты — рабочий резерв api/sse.js. */

import { API_URL, doFetch, enc, getHeaders, safeError } from './client';
import { watchTask } from './sse';

export const specsApi = {
  getSpecs: async (platform) => {
    const res = await doFetch(`${API_URL}/specs/${enc(platform)}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка получения спеков'));
    return res.json();
  },

  getSpecNames: async (platform) => {
    const res = await doFetch(`${API_URL}/specs/${enc(platform)}/names`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, `HTTP ${res.status}`));
    const d = await res.json();
    return (d.names || []).sort();
  },

  getSpec: async (platform, categoryId) => {
    const res = await doFetch(`${API_URL}/specs/${enc(platform)}/${enc(categoryId)}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка получения спека'));
    return res.json();
  },

  deleteSpec: async (platform, categoryId) => {
    const res = await doFetch(`${API_URL}/specs/${enc(platform)}/${enc(categoryId)}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка удаления спека'));
    return res.json();
  },

  deleteAllSpecs: async (platform) => {
    const res = await doFetch(`${API_URL}/specs/${enc(platform)}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка очистки спецификаций'));
    return res.json();
  },

  refreshSpecs: async (platform, apiKey, categoryIds = null, businessId = null) => {
    const res = await doFetch(`${API_URL}/specs/${enc(platform)}/refresh`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        api_key: apiKey,
        category_ids: categoryIds,
        business_id: businessId,
      }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка обновления спеков'));
    return res.json();
  },

  getSpecKeySource: async (platform) => {
    try {
      const res = await doFetch(`${API_URL}/specs/${enc(platform)}/key-source`, {
        headers: getHeaders(),
      });
      if (!res.ok) return { has_server_key: false };
      return await res.json();
    } catch {
      return { has_server_key: false };
    }
  },

  getSpecsRefreshProgress: async (platform, taskId) => {
    const res = await doFetch(`${API_URL}/specs/${enc(platform)}/refresh/${enc(taskId)}/progress`, {
      headers: getHeaders(),
    });
    if (!res.ok) return { status: 'unknown' };
    return res.json();
  },

  /* ✅ Round 8: прогресс фоновой загрузки спеков пушем (SSE), polling — резерв.
   * paused — терминальный: продолжение — на странице мониторинга. */
  streamSpecsRefresh: async (platform, taskId, { onUpdate, onError, signal, timeoutMs } = {}) => {
    return await watchTask(`${API_URL}/specs/${enc(platform)}/refresh/${enc(taskId)}/events`, {
      onEvent: onUpdate,
      onError,
      pollFallback: () => specsApi.getSpecsRefreshProgress(platform, taskId),
      isTerminal: (p) => ['completed', 'failed', 'paused'].includes(p?.status),
      signal,
      timeoutMs,
      pollIntervalMs: 1500,
    });
  },

  /* Мониторинг загрузок спеков — только для админа */
  getAdminSpecsTasks: async () => {
    const res = await doFetch(`${API_URL}/admin/specs-tasks`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки мониторинга спеков'));
    return res.json();
  },

  /* ✅ Round 8: живой мониторинг загрузок спеков (SSE-поток снимков).
   * Терминального статуса нет: поток живёт, пока страница открыта; сервер
   * закрывает его по лимиту времени — подключаемся заново (api/sse.js). */
  streamAdminSpecsTasks: async ({ onUpdate, onError, signal } = {}) => {
    return await watchTask(`${API_URL}/admin/specs-tasks/events`, {
      onEvent: onUpdate,
      onError,
      pollFallback: () => specsApi.getAdminSpecsTasks(),
      isTerminal: () => false,
      signal,
      pollIntervalMs: 3000,
    });
  },

  /* Пауза загрузки спеков (админ): задача дообработает текущий блок и остановится */
  pauseSpecsTask: async (taskId) => {
    const res = await doFetch(`${API_URL}/admin/specs-tasks/${enc(taskId)}/pause`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось поставить задачу на паузу'));
    return res.json();
  },

  /* Продолжить остановленную загрузку спеков (админ): новая задача с места остановки */
  resumeSpecsTask: async (taskId) => {
    const res = await doFetch(`${API_URL}/admin/specs-tasks/${enc(taskId)}/resume`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось возобновить загрузку'));
    return res.json();
  },
};
