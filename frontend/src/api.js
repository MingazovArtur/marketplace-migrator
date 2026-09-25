const API_URL = import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? '/api' : 'http://localhost:8000/api');

/* ---------- Вспомогательные функции ---------- */

// ✅ Все динамические сегменты пути (кириллица, пробелы, «→») обязаны кодироваться
const enc = encodeURIComponent;

const getHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
  };
};

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

async function safeError(res, fallback) {
  try {
    const data = await res.json();
    if (data.detail) {
      if (Array.isArray(data.detail)) {
        return data.detail
          .map((d) => `${(d.loc || []).join('.')} — ${d.msg}`)
          .join('; ');
      }
      // ✅ Поддержка структурированных ошибок (409 summary + problems и т.п.)
      if (typeof data.detail === 'object') {
        if (data.detail.message) return data.detail.message;
        return JSON.stringify(data.detail);
      }
      return String(data.detail);
    }
    return data.message || fallback;
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
}

/**
 * ✅ Извлечь имя файла из заголовка Content-Disposition.
 * Поддерживает RFC 5987:
 *   attachment; filename="fallback.xlsx"; filename*=UTF-8''%D0%9E...
 * Приоритет: filename*=UTF-8''... (оригинальное имя с кириллицей),
 *            затем filename="..." (fallback с латиницей).
 */
const parseContentDisposition = (header, fallback = 'export.xlsx') => {
  if (!header) return fallback;

  // Приоритет 1: RFC 5987 filename*=UTF-8''... (с кириллицей)
  const utf8Match = header.match(/filename\*\s*=\s*UTF-8''([^;\s]+)/i);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      // Если decode упал — падаем на обычный filename
    }
  }

  // Приоритет 2: filename="..." или filename=... (без кавычек)
  const quotedMatch = header.match(/filename\s*=\s*"([^"]+)"/i);
  if (quotedMatch) return quotedMatch[1];

  const plainMatch = header.match(/filename\s*=\s*([^;\s]+)/i);
  if (plainMatch) return plainMatch[1];

  return fallback;
};

/* ---------- API объект ---------- */

export const api = {
  /* ==================== Auth ==================== */

  login: async (credentials) => {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка входа'));
    return res.json();
  },

  register: async (payload) => {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка регистрации'));
    return res.json();
  },

  logout: () => {
    localStorage.removeItem('token');
  },

  getCurrentUser: async () => {
    const res = await fetch(`${API_URL}/auth/me`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось получить профиль'));
    return res.json();
  },

  getMe: async () => {
    const res = await fetch(`${API_URL}/auth/me`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось получить профиль'));
    return res.json();
  },

  /* ==================== Email (верификация + восстановление) ==================== */

  verifyEmail: async (token) => {
    const res = await fetch(`${API_URL}/auth/verify-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось подтвердить email'));
    return res.json();
  },

  resendVerification: async () => {
    const res = await fetch(`${API_URL}/auth/resend-verification`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось отправить письмо'));
    return res.json();
  },

  forgotPassword: async (email) => {
    const res = await fetch(`${API_URL}/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка запроса сброса'));
    return res.json();
  },

  resetPassword: async (token, newPassword) => {
    const res = await fetch(`${API_URL}/auth/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сбросить пароль'));
    return res.json();
  },

  /* ==================== Products ==================== */

  getProducts: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.search) q.append('search', params.search);
    if (params.status && params.status !== 'all') q.append('status', params.status);
    if (params.source && params.source !== 'all') q.append('source', params.source);
    if (params.sort_by) q.append('sort_by', params.sort_by);
    if (params.sort_order) q.append('sort_order', params.sort_order);
    if (params.skip !== undefined) q.append('skip', params.skip);
    if (params.limit !== undefined) q.append('limit', params.limit);

    const qs = q.toString();
    const url = `${API_URL}/products${qs ? '?' + qs : ''}`;
    const res = await fetch(url, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить товары'));
    return res.json();
  },

  deleteProduct: async (productId) => {
    const res = await fetch(`${API_URL}/products/${enc(productId)}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка удаления товара');
    }
    return res.json();
  },

  bulkDeleteProducts: async (productIds) => {
    const res = await fetch(`${API_URL}/products/bulk-delete`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_ids: productIds }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка массового удаления');
    }
    return res.json();
  },

  deleteAllProducts: async () => {
    const res = await fetch(`${API_URL}/products/delete-all`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ confirm: true }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка полного удаления');
    }
    return res.json();
  },

  bulkUpdateProducts: async (payload) => {
    const res = await fetch(`${API_URL}/products/bulk-update`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка массового обновления'));
    return res.json();
  },

  /* ==================== Product details ==================== */

  setAttributes: async (productId, attributes) => {
    const res = await fetch(`${API_URL}/products/${enc(productId)}/attributes`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(attributes),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения характеристик'));
    return res.json();
  },

  getVariants: async (productId) => {
    const res = await fetch(`${API_URL}/products/${enc(productId)}/variants`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки вариаций'));
    return res.json();
  },

  setVariants: async (productId, variants) => {
    const res = await fetch(`${API_URL}/products/${enc(productId)}/variants`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(variants),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения вариаций'));
    return res.json();
  },

  setPhotos: async (productId, photos) => {
    const res = await fetch(`${API_URL}/products/${enc(productId)}/photos`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify({ photos }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения фото'));
    return res.json();
  },

  downloadPhotos: async (productId) => {
    const res = await fetch(`${API_URL}/products/${enc(productId)}/photos/download`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка запуска скачивания'));
    return res.json();
  },

  /* ==================== Logistics ==================== */

  updateLogistics: async (productId, payload) => {
    const res = await fetch(`${API_URL}/products/${enc(productId)}/logistics`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка сохранения логистических данных');
    }
    return res.json();
  },

  // Алиас для обратной совместимости (LogisticsModal и др.)
  updateProductLogistics: (id, payload) => api.updateLogistics(id, payload),

  /* ==================== Platforms & categories ==================== */

  getPlatforms: async () => {
    const res = await fetch(`${API_URL}/platforms`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить платформы'));
    return res.json();
  },

  /**
   * ✅ Категории площадки.
   * ВАЖНО: маршрут /categories/{platform} на бэкенде существует НЕ для всех
   * источников (для source-строк вида «Магнит Маркет (Файл) → Ozon» его нет → 404).
   * Поэтому: кодируем путь и при 404 мягко возвращаем [] — UI покажет
   * предупреждение и предложит выбрать категорию из списка спеков.
   */
  getCategories: async (platform) => {
    const res = await fetch(`${API_URL}/categories/${enc(platform)}`, { headers: getHeaders() });
    if (res.status === 404) return [];
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить категории'));
    return res.json();
  },

  /**
   * ✅ Канонический эндпоинт маппинга категорий (в логах бэкенда отвечает 200).
   * Query-параметры кодирует URLSearchParams — кириллица и «→» безопасны.
   */
  getCategoryMapping: async (sourcePlatform, targetPlatform) => {
    const q = new URLSearchParams({
      source_platform: sourcePlatform || '',
      target_platform: targetPlatform || '',
    });
    const res = await fetch(`${API_URL}/category-mapping?${q.toString()}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить маппинг категорий'));
    return res.json();
  },

  /* ==================== Import ==================== */

  importProducts: async (authKey) => {
    const res = await fetch(`${API_URL}/import`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ url: 'mock', auth_key: authKey }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка импорта'));
    return res.json();
  },

  importFromFile: async (platform, file, mode = 'create') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('platform', platform);
    formData.append('mode', mode);
    const res = await fetch(`${API_URL}/import/file`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки файла'));
    return res.json();
  },

  /* ==================== Migration ==================== */

  previewMigration: async (productId, targetPlatform) => {
    const res = await fetch(`${API_URL}/migrate/preview`, {
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
    const res = await fetch(`${API_URL}/migrate/${enc(productId)}`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка миграции'));
    return res.json();
  },

  migrateBatch: async (productIds, platform) => {
    const ids = (productIds || [])
      .map((id) => Number(id))
      .filter((id) => !isNaN(id) && id > 0);
    if (!ids.length) throw new Error('Нет валидных товаров для миграции');

    const res = await fetch(`${API_URL}/migrate/batch`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_ids: ids, platform }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось запустить пакетную миграцию'));
    return res.json();
  },

  // Алиас для useMigration.js
  startBatchMigration: (ids, platform) => api.migrateBatch(ids, platform),

  // ✅ Прогресс Celery-задачи (миграция / specs refresh — один эндпоинт)
  getTaskProgress: async (taskId) => {
    const res = await fetch(`${API_URL}/migrate/batch/${enc(taskId)}/progress`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось получить прогресс'));
    return res.json();
  },

  getBatchProgress: (batchId) => api.getTaskProgress(batchId),

  /* ==================== Export ==================== */

  exportForPlatform: async (platform, status = 'success') => {
    const res = await fetch(
      `${API_URL}/export/platform/${enc(platform)}?status=${enc(status)}`,
      { headers: getHeaders() }
    );
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сформировать файл'));
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `upload_${platform}_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },

  exportPreview: async (platform, status = 'success') => {
    const res = await fetch(
      `${API_URL}/export/preview/${enc(platform)}?status=${enc(status)}`,
      { headers: getHeaders() }
    );
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка предпросмотра выгрузки'));
    return res.json();
  },

  exportTemplate: async (platform) => {
    const res = await fetch(`${API_URL}/export/template/${enc(platform)}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка скачивания шаблона'));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `template_${platform}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  exportReport: async () => {
    const res = await fetch(`${API_URL}/export/report`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сформировать отчет'));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `migration_report_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
    /* ==================== Эталонные шаблоны Ozon (файлы пользователя) ==================== */

  uploadOzonTemplate: async (categoryName, file) => {
    const fd = new FormData();
    fd.append('category_name', categoryName);
    fd.append('file', file);
    const res = await fetch(`${API_URL}/export/ozon-template/upload`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: fd,
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки эталонного шаблона'));
    return res.json();
  },

  listOzonTemplates: async () => {
    const res = await fetch(`${API_URL}/export/ozon-template/list`, { headers: getHeaders() });
    if (!res.ok) return { templates: [] };
    return res.json();
  },

  getOzonTemplateStatus: async (categoryName) => {
    const res = await fetch(
      `${API_URL}/export/ozon-template/status?category_name=${enc(categoryName)}`,
      { headers: getHeaders() }
    );
    if (!res.ok) return { has_official_template: false };
    return res.json();
  },

  deleteOzonTemplate: async (categoryName) => {
    const res = await fetch(
      `${API_URL}/export/ozon-template?category_name=${enc(categoryName)}`,
      { method: 'DELETE', headers: getHeaders() }
    );
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка удаления эталона'));
    return res.json();
  },

  /**
   * ✅ Валидация готовности товаров к экспорту.
   * @param {string} platform - площадка (ozon, yandex, wildberries)
   * @param {string} status - фильтр по статусу (success, pending, all)
   * @param {number|null} productId - ID одного товара (для модалки миграции)
   */
  validateExport: async (platform, status = 'all', productId = null) => {
    const q = new URLSearchParams();
    if (status) q.append('status', status);
    if (productId) q.append('product_id', productId);

    const res = await fetch(`${API_URL}/export/validate/${enc(platform)}?${q.toString()}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка проверки готовности к экспорту'));
    return res.json();
  },

  /**
   * ✅ XLSX v2: файл под реальный шаблон площадки.
   *
   * @param {string} platform - площадка (ozon, yandex, wildberries)
   * @param {string} status - фильтр по статусу (success, pending, all)
   * @param {number|null} productId - ID одного товара (для авто-экспорта из модалки миграции)
   *
   * 409 — структурированный detail (summary + fix_hint).
   * 400 — валидатор не пропустил ни один товар: показываем detail целиком.
   *
   * ✅ Поддержка RFC 5987 filename*: имя с кириллицей в загрузках браузера.
   */
  exportXlsxV2: async (platform, status = 'success', productId = null) => {
    const q = new URLSearchParams();
    if (status) q.append('status', status);
    if (productId) q.append('product_id', productId);  // ✅ фильтр по одному товару

    const res = await fetch(`${API_URL}/export/xlsx/${enc(platform)}?${q.toString()}`, {
      headers: getHeaders(),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));

      if (res.status === 409 && data.detail && typeof data.detail === 'object') {
        const sum = Object.entries(data.detail.summary || {})
          .map(([k, v]) => `${k}: ${v.count} шт.`)
          .join(', ');
        const hint = data.detail.fix_hint ? `\n\n${data.detail.fix_hint}` : '';
        throw new Error(`${data.detail.message}\nПроблемы: ${sum}${hint}`);
      }

      if (res.status === 400) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : (data.detail?.message || JSON.stringify(data.detail || {}));

        // ✅ Для одиночного товара — просто показываем конкретные ошибки
        if (productId) {
          throw new Error(
            `Товар #${productId} не прошёл валидацию:\n\n${detail}\n\n` +
            `Исправьте поля через кнопки «Логистика», «Характеристики», «Фото» и повторите миграцию.`
          );
        }

        throw new Error(
          `${detail}\n\nОткройте «Выгрузка» — блок валидации покажет, каких полей не хватает каждому товару.`
        );
      }

      throw new Error(await safeError(res, `HTTP ${res.status}`));
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;

    // ✅ RFC 5987: сначала пытаемся filename*=UTF-8''... (кириллица), потом filename=...
    const cd = res.headers.get('content-disposition');
    const filename = parseContentDisposition(cd, `${platform}_export.xlsx`);

    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return filename;
  },

  /* ==================== Stats / History ==================== */

  getStats: async () => {
    const res = await fetch(`${API_URL}/stats`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить статистику'));
    return res.json();
  },

  getHistory: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.operation) q.append('operation', params.operation);
    if (params.limit) q.append('limit', params.limit);
    const qs = q.toString();
    const res = await fetch(`${API_URL}/history${qs ? '?' + qs : ''}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить историю'));
    return res.json();
  },

  /* ==================== Спецификации категорий площадок ==================== */

  getSpecs: async (platform) => {
    const res = await fetch(`${API_URL}/specs/${enc(platform)}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка получения спеков'));
    return res.json();
  },

  // ✅ ЛЁГКИЙ список имён категорий (для datalist модалки миграции и страницы спеков)
  getSpecNames: async (platform) => {
    const res = await fetch(`${API_URL}/specs/${enc(platform)}/names`, { headers: getHeaders() });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    return (d.names || []).sort();
  },

  getSpec: async (platform, categoryId) => {
    const res = await fetch(
      `${API_URL}/specs/${enc(platform)}/${enc(categoryId)}`,
      { headers: getHeaders() }
    );
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка получения спека'));
    return res.json();
  },

  refreshSpecs: async (platform, apiKey, categoryIds = null, businessId = null) => {
    const res = await fetch(`${API_URL}/specs/${enc(platform)}/refresh`, {
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
      const res = await fetch(`${API_URL}/specs/${enc(platform)}/key-source`, {
        headers: getHeaders(),
      });
      if (!res.ok) return { has_server_key: false };
      return await res.json();
    } catch {
      return { has_server_key: false };
    }
  },

  getSpecsRefreshProgress: async (platform, taskId) => {
    const res = await fetch(
      `${API_URL}/specs/${enc(platform)}/refresh/${enc(taskId)}/progress`,
      { headers: getHeaders() }
    );
    if (!res.ok) return { status: 'unknown' };
    return res.json();
  },

    /* ==================== Дефолты экспорта ==================== */

  getDefaults: async () => {
    const res = await fetch(`${API_URL}/defaults`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить дефолты'));
    return res.json();
  },

  saveDefaults: async (payload) => {
    const res = await fetch(`${API_URL}/defaults`, {
      method: 'PUT', headers: getHeaders(), body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сохранить дефолты'));
    return res.json();
  },

  deleteCategoryDefaults: async (categoryName) => {
    const res = await fetch(`${API_URL}/defaults/category?category_name=${enc(categoryName)}`, {
      method: 'DELETE', headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось удалить дефолты категории'));
    return res.json();
  },

  getGaps: async (status = 'all') => {
    const res = await fetch(`${API_URL}/defaults/gaps?status=${enc(status)}`, { headers: getHeaders() });
    if (!res.ok) return { total: 0, gaps: {} };
    return res.json();
  },

  applyDefaults: async (status = 'all') => {
    const res = await fetch(`${API_URL}/products/apply-defaults?status=${enc(status)}`, {
      method: 'POST', headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось заполнить пропуски'));
    return res.json();
  },
};