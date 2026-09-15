const API_URL = 'http://localhost:8000/api';

// Функция для получения заголовков с токеном авторизации
const getHeaders = () => {
  const token = localStorage.getItem('token');
  
  // 🔍 ОТЛАДКА: Смотрим в консоль браузера, что именно мы отправляем
  console.log('🔑 Отправляемый токен:', token ? `${token.substring(0, 20)}...` : 'ОТСУТСТВУЕТ');
  
  const headers = {
    'Content-Type': 'application/json',
    ...(token && { 'Authorization': `Bearer ${token}` })
  };
  
  console.log('📦 Итоговые заголовки:', headers);
  return headers;
};

// Функция для получения заголовков без Content-Type (для FormData)
const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    ...(token && { 'Authorization': `Bearer ${token}` })
  };
};

export const api = {
  // === АВТОРИЗАЦИЯ ===
  
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

  // === ТОВАРЫ ===

  getStats: async () => {
    const res = await fetch(`${API_URL}/stats`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Не удалось загрузить статистику');
    return res.json();
  },

  getProducts: async () => {
    const res = await fetch(`${API_URL}/products`, {
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

  // === ПЛАТФОРМЫ И КАТЕГОРИИ ===

  getPlatforms: async () => {
    const res = await fetch(`${API_URL}/platforms`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Не удалось загрузить платформы');
    return res.json();
  },

  getCategories: async (platform) => {
    const res = await fetch(`${API_URL}/categories/${platform}`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Не удалось загрузить категории');
    return res.json();
  },

  // === ИМПОРТ ===

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
      headers: getAuthHeaders(), // Не устанавливаем Content-Type для FormData
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки файла');
    return data;
  },

  // === МИГРАЦИЯ ===

  previewMigration: async (productId, targetPlatform) => {
    const res = await fetch(`${API_URL}/migrate/preview`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ 
        product_id: productId, 
        target_marketplace: targetPlatform 
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка предпросмотра');
    return data;
  },

  migrateProduct: async (productId, targetPlatform, editedData = null) => {
    const body = {
      product_id: productId,
      target_marketplace: targetPlatform
    };
    
    if (editedData) {
      body.edited_data = editedData;
    }
    
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
      body: JSON.stringify({ 
        product_ids: productIds, 
        target_marketplace: targetPlatform 
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка пакетной миграции');
    return data;
  },

  getTaskProgress: async (taskId) => {
    const res = await fetch(`${API_URL}/tasks/${taskId}/progress`, {
      headers: getHeaders()
    });
    const data = await res.json();
    if (!res.ok) throw new Error('Не удалось получить прогресс');
    return data.progress || data;
  },

  // === ЭКСПОРТ ===

  exportReport: async () => {
    const res = await fetch(`${API_URL}/export/report`, {
      headers: getHeaders()
    });
    if (!res.ok) throw new Error('Не удалось сформировать отчет');
    
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const dateStr = new Date().toISOString().slice(0, 10);
    a.download = `migration_report_${dateStr}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  }
};