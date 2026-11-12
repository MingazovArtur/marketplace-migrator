/* Товары: список/CRUD/массовые операции/ТН ВЭД/подробности/логистика
 * (Р5: вынесено из api.js — секции «Products», «Product details», «Logistics»). */

import { API_URL, doFetch, enc, getAuthHeaders, getHeaders, safeError } from './client';

export const productsApi = {
  getProducts: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.search) q.append('search', params.search);
    if (params.status && params.status !== 'all') q.append('status', params.status);
    if (params.source && params.source !== 'all') q.append('source', params.source);
    if (params.sort) q.append('sort', params.sort);
    if (params.sort_by) q.append('sort_by', params.sort_by);
    if (params.sort_order) q.append('sort_order', params.sort_order);
    if (params.skip !== undefined) q.append('skip', params.skip);
    if (params.limit !== undefined) q.append('limit', params.limit);

    const qs = q.toString();
    const res = await doFetch(`${API_URL}/products${qs ? '?' + qs : ''}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить товары'));
    return res.json();
  },

  /* Один товар со свежими данными из БД (модалки: миграция/логистика/фото).
     Кэш списка на фронте может устареть после «Заполнить пропуски»/массовых
     обновлений — этот запрос всегда возвращает актуальную цену и поля. */
  getProduct: async (productId) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить товар'));
    return res.json();
  },

  deleteProduct: async (productId) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка удаления товара'));
    return res.json();
  },

  bulkDeleteProducts: async (productIds) => {
    const res = await doFetch(`${API_URL}/products/bulk-delete`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_ids: productIds }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка массового удаления'));
    return res.json();
  },

  deleteAllProducts: async () => {
    const res = await doFetch(`${API_URL}/products/delete-all`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ confirm: true }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка полного удаления'));
    return res.json();
  },

  bulkUpdateProducts: async (payload) => {
    const res = await doFetch(`${API_URL}/products/bulk-update`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка массового обновления'));
    return res.json();
  },

  /* Предпросмотр массового обновления без записи: цены до/после + валидность категории */
  bulkPreviewProducts: async (payload) => {
    const res = await doFetch(`${API_URL}/products/bulk-preview`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка предпросмотра'));
    return res.json();
  },

  /* ✅ v4: отмена операции правки — последней или по snapshot_id (аудит-лог) */
  bulkUndoProducts: async (snapshotId = null) => {
    const res = await doFetch(`${API_URL}/products/bulk-undo`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(snapshotId ? { snapshot_id: snapshotId } : {}),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось отменить обновление'));
    return res.json();
  },

  /* ✅ v4: лента последних операций правки товаров (аудит-лог) */
  getEditHistory: async (limit = 20) => {
    const res = await doFetch(`${API_URL}/products/edit-history?limit=${enc(limit)}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить историю изменений'));
    return res.json();
  },

  /* ✅ v4: массовый подбор ТН ВЭД — кандидаты по выбранным товарам */
  tnvedBatchSuggest: async (productIds) => {
    const res = await doFetch(`${API_URL}/tnved/batch-suggest`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_ids: productIds }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось подобрать ТН ВЭД'));
    return res.json();
  },

  /* ✅ v4: массовое применение кода ТН ВЭД к выбранным товарам (undo-able) */
  tnvedBatchApply: async (productIds, code) => {
    const res = await doFetch(`${API_URL}/tnved/batch-apply`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_ids: productIds, code }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось применить код ТН ВЭД'));
    return res.json();
  },

  /* ✅ О3: лёгкие счётчики товаров по категориям назначения (один GROUP BY).
     Заменяет выгрузку 10 000 товаров ради блока «Недостающие шаблоны»
     в окне экспорта. */
  getCategoryCounts: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.status && params.status !== 'all') q.append('status', params.status);
    if (params.productIds && params.productIds.length > 0) {
      q.append('product_ids', params.productIds.join(','));
    }
    const qs = q.toString();
    const res = await doFetch(`${API_URL}/products/category-counts${qs ? '?' + qs : ''}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить категории'));
    const d = await res.json();
    return d.counts || {};
  },

  /* Подсказки категорий назначения из спеков площадок (автокомплит) */
  categorySuggestions: async (q = '', limit = 15) => {
    const query = new URLSearchParams({ q, limit: String(limit) }).toString();
    const res = await doFetch(`${API_URL}/products/categories-suggest?${query}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить подсказки'));
    return res.json();
  },

  /* Точечное обновление товара — кнопка «Сохранить» в окне миграции */
  updateProduct: async (productId, payload) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения товара'));
    return res.json();
  },

  /* ---------- Product details ---------- */

  setAttributes: async (productId, attributes) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}/attributes`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(attributes),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения характеристик'));
    return res.json();
  },

  getVariants: async (productId) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}/variants`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки вариаций'));
    return res.json();
  },

  setVariants: async (productId, variants) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}/variants`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(variants),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения вариаций'));
    return res.json();
  },

  setPhotos: async (productId, photos) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}/photos`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify({ photos }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения фото'));
    return res.json();
  },

  uploadProductPhotos: async (productId, files) => {
    const fd = new FormData();
    Array.from(files || []).forEach((f) => fd.append('files', f));
    const res = await doFetch(`${API_URL}/products/${enc(productId)}/photos/upload`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: fd,
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки файлов изображений'));
    return res.json();
  },

  downloadPhotos: async (productId) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}/photos/download`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка запуска скачивания'));
    return res.json();
  },

  /* ---------- Logistics ---------- */

  updateLogistics: async (productId, payload) => {
    const res = await doFetch(`${API_URL}/products/${enc(productId)}/logistics`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения логистических данных'));
    return res.json();
  },

  updateProductLogistics: (id, payload) => productsApi.updateLogistics(id, payload),
};
