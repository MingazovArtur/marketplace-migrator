const API_URL = import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? '/api' : 'http://localhost:8000/api');

/* ---------- Вспомогательные функции ---------- */

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
      // ✅ Поддержка структурированного 409 (summary + problems)
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
    if (params.status) q.append('status', params.status);
    if (params.source) q.append('source', params.source);
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
    const res = await fetch(`${API_URL}/products/${productId}`, {
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
    const res = await fetch(`${API_URL}/products/${productId}/attributes`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(attributes),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения характеристик'));
    return res.json();
  },

  getVariants: async (productId) => {
    const res = await fetch(`${API_URL}/products/${productId}/variants`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки вариаций'));
    return res.json();
  },

  setVariants: async (productId, variants) => {
    const res = await fetch(`${API_URL}/products/${productId}/variants`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(variants),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения вариаций'));
    return res.json();
  },

  setPhotos: async (productId, photos) => {
    const res = await fetch(`${API_URL}/products/${productId}/photos`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify({ photos }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка сохранения фото'));
    return res.json();
  },

  downloadPhotos: async (productId) => {
    const res = await fetch(`${API_URL}/products/${productId}/photos/download`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка запуска скачивания'));
    return res.json();
  },

  /* ==================== Logistics (единый канонический метод) ==================== */

  updateLogistics: async (productId, payload) => {
    const res = await fetch(`${API_URL}/products/${productId}/logistics`, {
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

  // Алиас для обратной совместимости
  updateProductLogistics: (id, payload) => api.updateLogistics(id, payload),

  /* ==================== Platforms & categories ==================== */

  getPlatforms: async () => {
    const res = await fetch(`${API_URL}/platforms`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить платформы'));
    return res.json();
  },

  getCategories: async (platform) => {
    const res = await fetch(`${API_URL}/categories/${platform}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось загрузить категории'));
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
    const res = await fetch(`${API_URL}/migrate/${productId}`, {
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
    const res = await fetch(`${API_URL}/migrate/batch/${taskId}/progress`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось получить прогресс'));
    return res.json();
  },

  getBatchProgress: (batchId) => api.getTaskProgress(batchId),

  /* ==================== Export ==================== */

  exportForPlatform: async (platform, status = 'success') => {
    const res = await fetch(`${API_URL}/export/platform/${platform}?status=${status}`, {
      headers: getHeaders(),
    });
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
    const res = await fetch(`${API_URL}/export/preview/${platform}?status=${status}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка предпросмотра выгрузки'));
    return res.json();
  },

  exportTemplate: async (platform) => {
    const res = await fetch(`${API_URL}/export/template/${platform}`, { headers: getHeaders() });
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

  validateExport: async (platform) => {
    const res = await fetch(`${API_URL}/export/validate/${platform}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка проверки готовности к экспорту'));
    return res.json();
  },

  // ✅ XLSX v2: детальный 409 с summary и fix_hint
  exportXlsxV2: async (platform, status = 'success') => {
    const res = await fetch(`${API_URL}/export/xlsx/${platform}?status=${status}`, { headers: getHeaders() });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (res.status === 409 && data.detail) {
        if (typeof data.detail === 'object') {
          const sum = Object.entries(data.detail.summary || {})
            .map(([k, v]) => `${k}: ${v.count} шт.`)
            .join(', ');
          const hint = data.detail.fix_hint ? `\n\n${data.detail.fix_hint}` : '';
          throw new Error(`${data.detail.message}\nПроблемы: ${sum}${hint}`);
        }
        throw new Error(data.detail);
      }
      throw new Error(await safeError(res, `HTTP ${res.status}`));
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const filename = res.headers.get('content-disposition')?.split('filename=')[1]?.replace(/"/g, '')
                 || `${platform}_export.xlsx`;
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
    const res = await fetch(`${API_URL}/specs/${platform}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка получения спеков'));
    return res.json();
  },

  // ✅ ЛЁГКИЙ список имён (только category_name) — для datalist в модалке миграции
  getSpecNames: async (platform) => {
    const res = await fetch(`${API_URL}/specs/${platform}/names`, { headers: getHeaders() });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    return (d.names || []).sort();
  },
  getSpec: async (platform, categoryId) => {
    const res = await fetch(`${API_URL}/specs/${platform}/${categoryId}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка получения спека'));
    return res.json();
  },

  refreshSpecs: async (platform, apiKey, categoryIds = null, businessId = null) => {
    const res = await fetch(`${API_URL}/specs/${platform}/refresh`, {
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
      const res = await fetch(`${API_URL}/specs/${platform}/key-source`, {
        headers: getHeaders(),
      });
      if (!res.ok) return { has_server_key: false };
      return await res.json();
    } catch {
      return { has_server_key: false };
    }
  },

  getSpecsRefreshProgress: async (platform, taskId) => {
    const res = await fetch(`${API_URL}/specs/${platform}/refresh/${taskId}/progress`, {
      headers: getHeaders(),
    });
    if (!res.ok) return { status: 'unknown' };
    return res.json();
  },
};