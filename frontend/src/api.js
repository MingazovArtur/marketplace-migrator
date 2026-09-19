const API_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '/api' : 'http://localhost:8000/api');

const authHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

async function safeError(res, fallback) {
  try {
    const data = await res.json();
    if (data.detail) {
      return Array.isArray(data.detail)
        ? data.detail.map(d => `${(d.loc || []).join('.')} — ${d.msg}`).join('; ')
        : String(data.detail);
    }
    return data.message || fallback;
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
}



const getHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token && { 'Authorization': `Bearer ${token}` })
  };
};

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    ...(token && { 'Authorization': `Bearer ${token}` })
  };
};

export const api = {
  login: async (credentials) => {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
    });
    const data = await res.json();
    if (!res.ok) {
      // ✅ Правильное извлечение ошибки из FastAPI 422
      if (data.detail) {
        if (Array.isArray(data.detail)) {
          // Pydantic validation errors
          const messages = data.detail.map(err => err.msg || 'Ошибка валидации');
          throw new Error(messages.join(', '));
        } else {
          // Обычная ошибка (например, неверный пароль)
          throw new Error(data.detail);
        }
      }
      throw new Error('Ошибка входа');
    }
    return data;
  },

  register: async (userData) => {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userData),
    });
    const data = await res.json();
    if (!res.ok) {
      // ✅ Правильное извлечение ошибки
      if (data.detail) {
        if (Array.isArray(data.detail)) {
          const messages = data.detail.map(err => err.msg || 'Ошибка валидации');
          throw new Error(messages.join(', '));
        } else {
          throw new Error(data.detail);
        }
      }
      throw new Error('Ошибка регистрации');
    }
    return data;
  },

  logout: () => {
    localStorage.removeItem('token');
  },

  getCurrentUser: async () => {
    const res = await fetch(`${API_URL}/auth/me`, {
      headers: getHeaders()
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Не удалось получить данные пользователя');
    return data;
  },

  getStats: async () => {
    const res = await fetch(`${API_URL}/stats`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Не удалось загрузить статистику');
    return res.json();
  },

  getProducts: async (params = {}) => {
    const queryParams = new URLSearchParams();
    
    if (params.search) queryParams.append('search', params.search);
    if (params.status) queryParams.append('status', params.status);
    if (params.source) queryParams.append('source', params.source);
    if (params.sort_by) queryParams.append('sort_by', params.sort_by);
    if (params.sort_order) queryParams.append('sort_order', params.sort_order);
    if (params.skip !== undefined) queryParams.append('skip', params.skip);
    if (params.limit !== undefined) queryParams.append('limit', params.limit);
    
    const queryString = queryParams.toString();
    const url = `${API_URL}/products${queryString ? '?' + queryString : ''}`;
    
    const res = await fetch(url, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Не удалось загрузить товары');
    return res.json();
  },

  deleteProduct: async (productId) => {
    const res = await fetch(`${API_URL}/products/${productId}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Не удалось удалить товар');
    return res.json();
  },

  getPlatforms: async () => {
    const res = await fetch(`${API_URL}/platforms`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Не удалось загрузить платформы');
    return res.json();
  },

  getCategories: async (platform) => {
    const res = await fetch(`${API_URL}/categories/${platform}`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Не удалось загрузить категории');
    return res.json();
  },

  importProducts: async (authKey) => {
    const res = await fetch(`${API_URL}/import`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ url: 'mock', auth_key: authKey })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка импорта');
    return data;
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
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки файла');
    return data;
  },

  bulkUpdateProducts: async (payload) => {
    const res = await fetch(`${API_URL}/products/bulk-update`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка массового обновления');
    return data;
  },

  previewMigration: async (productId, targetPlatform) => {
    const res = await fetch(`${API_URL}/migrate/preview`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_id: productId, target_marketplace: targetPlatform })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка предпросмотра');
    return data;
  },

  exportForPlatform: async (platform, status = 'success') => {
    const res = await fetch(`${API_URL}/export/platform/${platform}?status=${status}`, { headers: getHeaders() });
    if (!res.ok) {
      const d = await res.json().catch(() => null);
      throw new Error(d?.detail || 'Не удалось сформировать файл');
    }
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

  migrateProduct: async (productId, targetPlatform, editedData = null) => {
    const body = { product_id: productId, target_marketplace: targetPlatform };
    if (editedData) body.edited_data = editedData;
    const res = await fetch(`${API_URL}/migrate`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка миграции');
    return data;
  },

  migrateBatch: async (productIds, platform) => {
    const ids = productIds.map(id => Number(id)).filter(id => !isNaN(id) && id > 0);
    if (ids.length === 0) throw new Error('Нет валидных товаров для миграции');

    const res = await fetch(`${API_URL}/migrate/batch`, {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_ids: ids,        // ✅ массив чисел
        platform: platform,      // ✅ строка: ozon | wildberries | yandex | magnit
      }),
    });

    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const errData = await res.json();
        if (errData.detail) {
          if (Array.isArray(errData.detail)) {
            msg = errData.detail.map(d => `${d.loc?.join('.')} — ${d.msg}`).join('; ');
          } else {
            msg = errData.detail;
          }
        }
      } catch { /* не JSON */ }
      throw new Error(msg);
    }
    return res.json();
  },
  getTaskProgress: async (taskId) => {
    const res = await fetch(`${API_URL}/tasks/${taskId}/progress`, { headers: getHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error('Не удалось получить прогресс');
    return data.progress || data;
  },

  bulkUpdateProducts: async (payload) => {
    const res = await fetch(`${API_URL}/products/bulk-update`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка массового обновления');
    return data;
  },

  exportReport: async () => {
    const res = await fetch(`${API_URL}/export/report`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Не удалось сформировать отчет');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `migration_report_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },

  exportPreview: async (platform, status = 'success') => {
    const res = await fetch(`${API_URL}/export/preview/${platform}?status=${status}`, {
      headers: getHeaders(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка предпросмотра выгрузки');
    return data;
  },

  exportTemplate: async (platform) => {
    const res = await fetch(`${API_URL}/export/template/${platform}`, { headers: getHeaders() });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Ошибка скачивания шаблона');
    }
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

  getHistory: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.operation) q.append('operation', params.operation);
    if (params.limit) q.append('limit', params.limit);
    const qs = q.toString();
    const res = await fetch(`${API_URL}/history${qs ? '?' + qs : ''}`, { headers: getHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Не удалось загрузить историю');
    return data;
  },

  getMe: async () => {
    const res = await fetch(`${API_URL}/auth/me`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Не удалось получить профиль');
    return res.json();
  },

  register: async (payload) => {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка регистрации');
    return data;
  },

  setAttributes: async (productId, attributes) => {
    const res = await fetch(`${API_URL}/products/${productId}/attributes`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(attributes),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка сохранения характеристик');
    return data;
  },

    getVariants: async (productId) => {
    const res = await fetch(`${API_URL}/products/${productId}/variants`, { headers: getHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки вариаций');
    return data;
  },

  setVariants: async (productId, variants) => {
    const res = await fetch(`${API_URL}/products/${productId}/variants`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(variants),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка сохранения вариаций');
    return data;
  },

  setPhotos: async (productId, photos) => {
    const res = await fetch(`${API_URL}/products/${productId}/photos`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify({ photos }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка сохранения фото');
    return data;
  },

  startBatchMigration: async (ids, platform) => {
    const res = await fetch(`${API_URL}/migrate/batch`, {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_ids: ids, platform }),
    });
    if (!res.ok) throw new Error('Не удалось запустить миграцию');
    return res.json();
  },

  getBatchProgress: async (batchId) => {
    const res = await fetch(`${API_URL}/migrate/batch/${batchId}/progress`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error('Не удалось получить прогресс миграции');
    return res.json();
  },

  downloadPhotos: async (productId) => {
    const res = await fetch(`${API_URL}/products/${productId}/photos/download`, {
      method: 'POST',
      headers: getHeaders(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка запуска скачивания');
    return data;
  },

};