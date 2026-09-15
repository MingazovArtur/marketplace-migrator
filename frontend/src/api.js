const API_URL = 'http://localhost:8000/api';

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
  login: async (username, password) => {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка входа');
    return data;
  },

  register: async (email, username, password) => {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, username, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка регистрации');
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

  importFromFile: async (platform, file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_URL}/import/file?platform=${platform}`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки файла');
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

  migrateBatch: async (productIds, targetPlatform) => {
    const res = await fetch(`${API_URL}/migrate/batch`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ product_ids: productIds, target_marketplace: targetPlatform })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка пакетной миграции');
    return data;
  },

  getTaskProgress: async (taskId) => {
    const res = await fetch(`${API_URL}/tasks/${taskId}/progress`, { headers: getHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error('Не удалось получить прогресс');
    return data.progress || data;
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
  }
};