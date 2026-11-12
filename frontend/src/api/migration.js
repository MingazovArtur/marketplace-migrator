/* Миграция: точечная/пакетная, прогресс задач, ✅ v4 профили миграции
 * (Р5: вынесено из api.js — секции «Migration» и «профили миграции»).
 *
 * Round 8: прогресс — SSE-поток (streamTaskProgress); старые polling-эндпоинты
 * остаются рабочим резервом (используются api/sse.js при сбое SSE). */

import { API_URL, doFetch, enc, getAuthHeaders, getHeaders, safeError } from './client';
import { watchTask } from './sse';

export const migrationApi = {
  previewMigration: async (productId, targetPlatform) => {
    const res = await doFetch(`${API_URL}/migrate/preview`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_id: productId, target_marketplace: targetPlatform }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка предпросмотра'));
    return res.json();
  },

  migrateProduct: async (productId, targetPlatform, editedData = null) => {
    const body = { platform: targetPlatform };
    if (editedData) body.edited_data = editedData;
    const res = await doFetch(`${API_URL}/migrate/${enc(productId)}`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка миграции'));
    return res.json();
  },

  migrateBatch: async (productIds, platform) => {
    const ids = (productIds || []).map((id) => Number(id)).filter((id) => !isNaN(id) && id > 0);
    if (!ids.length) throw new Error('Нет валидных товаров для миграции');

    const res = await doFetch(`${API_URL}/migrate/batch`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_ids: ids, platform }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось запустить пакетную миграцию'));
    return res.json();
  },

  startBatchMigration: (ids, platform) => migrationApi.migrateBatch(ids, platform),

  getTaskProgress: async (taskId) => {
    const res = await doFetch(`${API_URL}/migrate/batch/${enc(taskId)}/progress`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось получить прогресс'));
    return res.json();
  },

  getBatchProgress: (batchId) => migrationApi.getTaskProgress(batchId),

  /* ✅ Round 8: прогресс миграции пушем (SSE), polling — автоматический резерв.
   * Резолвится терминальным кадром (completed/failed); onUpdate — каждый кадр. */
  streamTaskProgress: async (
    taskId,
    { onUpdate, onError, signal, timeoutMs, timeoutMessage, pollIntervalMs } = {}
  ) => {
    return await watchTask(`${API_URL}/migrate/batch/${enc(taskId)}/events`, {
      onEvent: onUpdate,
      onError,
      pollFallback: () => migrationApi.getTaskProgress(taskId),
      signal,
      timeoutMs,
      timeoutMessage,
      pollIntervalMs,
    });
  },

  /* ---------- ✅ v4: профили миграции (площадка + дефолты) ---------- */

  getMigrationProfiles: async () => {
    const res = await doFetch(`${API_URL}/migration-profiles`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить профили'));
    return res.json();
  },

  saveMigrationProfile: async (payload) => {
    const res = await doFetch(`${API_URL}/migration-profiles`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сохранить профиль'));
    return res.json();
  },

  deleteMigrationProfile: async (profileId) => {
    const res = await doFetch(`${API_URL}/migration-profiles/${enc(profileId)}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось удалить профиль'));
    return res.json();
  },

  applyMigrationProfile: async (profileId) => {
    const res = await doFetch(`${API_URL}/migration-profiles/${enc(profileId)}/apply`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось применить профиль'));
    return res.json();
  },
};
