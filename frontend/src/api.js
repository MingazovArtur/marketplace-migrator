const API_URL = 'http://localhost:8000/api';

export const api = {
  getStats: async () => {
    const res = await fetch(`${API_URL}/stats`);
    if (!res.ok) throw new Error('Не удалось загрузить статистику');
    return res.json();
  },

  getProducts: async () => {
    const res = await fetch(`${API_URL}/products`);
    if (!res.ok) throw new Error('Не удалось загрузить товары');
    return res.json();
  },

  getPlatforms: async () => {
    const res = await fetch(`${API_URL}/platforms`);
    return res.json();
  },

  getCategories: async (platform) => {
    const res = await fetch(`${API_URL}/categories/${platform}`);
    return res.json();
  },

  importProducts: async (authKey) => {
    const res = await fetch(`${API_URL}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: 'mock', auth_key: authKey })
    });
    
    const data = await res.json();
    
    // <-- ДОБАВЛЕНО: выбрасываем точную ошибку от бэкенда
    if (!res.ok) {
      throw new Error(data.detail || 'Ошибка импорта');
    }
    
    return data;
  },

  migrateProduct: async (productId, targetPlatform) => {
    const res = await fetch(`${API_URL}/migrate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, target_marketplace: targetPlatform })
    });
    
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Ошибка миграции');
    }
    
    return data;
  },

  deleteProduct: async (productId) => {
    const res = await fetch(`${API_URL}/products/${productId}`, { method: 'DELETE' });
    return res.json();
  }
};