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
    
    if (!res.ok) {
      throw new Error(data.detail || 'Ошибка импорта');
    }
    
    return data;
  },

  importFromFile: async (platform, file) => {
    const formData = new FormData();
    formData.append('file', file);
    
    const res = await fetch(`${API_URL}/import/file?platform=${platform}`, {
      method: 'POST',
      body: formData
    });
    
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Ошибка загрузки файла');
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
    previewMigration: async (productId, targetPlatform) => {
    const res = await fetch(`${API_URL}/migrate/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, target_marketplace: targetPlatform })
    });
    
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка предпросмотра');
    return data;
  },
  
    exportReport: async () => {
    const res = await fetch(`${API_URL}/export/report`);
    if (!res.ok) throw new Error('Не удалось сформировать отчет');
    
    // Получаем данные как Blob (бинарный файл)
    const blob = await res.blob();
    
    // Создаем временную ссылку для скачивания
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    
    // Генерируем имя файла с текущей датой
    const dateStr = new Date().toISOString().slice(0, 10);
    a.download = `migration_report_${dateStr}.xlsx`;
    
    // Эмулируем клик по ссылке
    document.body.appendChild(a);
    a.click();
    
    // Убираем следы
    a.remove();
    window.URL.revokeObjectURL(url);
  },

  deleteProduct: async (productId) => {
    const res = await fetch(`${API_URL}/products/${productId}`, { method: 'DELETE' });
    return res.json();
  }

  
};