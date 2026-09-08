import React, { useState, useEffect } from 'react';
import './App.css';

const API_URL = 'http://localhost:8000/api';

function App() {
  const [stats, setStats] = useState({ total: 0, pending: 0, success: 0, error: 0 });
  const [products, setProducts] = useState([]);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importUrl, setImportUrl] = useState('');
  const [authKey, setAuthKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, productsRes] = await Promise.all([
        fetch(`${API_URL}/stats`),
        fetch(`${API_URL}/products`)
      ]);
      const statsData = await statsRes.json();
      const productsData = await productsRes.json();
      setStats(statsData);
      setProducts(productsData.products || []);
    } catch (error) {
      console.error('Ошибка загрузки:', error);
      setMessage('❌ Не удалось подключиться к бэкенду');
    }
  };

  const handleImport = async () => {
    if (!authKey) {
      setMessage('⚠️ Введите ключ авторизации');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch(`${API_URL}/import/ozon`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: importUrl || 'mock', auth_key: authKey })
      });
      const data = await response.json();
      if (data.success) {
        setMessage(`✅ Импортировано ${data.imported} товаров${data.is_mock ? ' (тестовый режим)' : ''}`);
        setImportUrl('');
        setAuthKey('');
        setShowImportModal(false);
        loadData();
      } else {
        setMessage('❌ Ошибка импорта: ' + (data.detail || 'неизвестно'));
      }
    } catch (error) {
      setMessage('❌ Ошибка соединения с сервером: ' + error.message);
    }
    setLoading(false);
  };

      const handleMigrate = async (productId) => {
    const target = window.confirm("Перенести этот товар на Wildberries?\n\nСистема автоматически подберет подходящую категорию.") ? "wildberries" : null;
    
    if (!target) return;
    
    setLoading(true);
    setMessage("⏳ Идет перенос товара и маппинг категорий...");
    
    try {
      const response = await fetch(`${API_URL}/migrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: productId, target_marketplace: target })
      });
      const data = await response.json();
      
      if (data.success) {
        // Показываем красивое сообщение с результатом маппинга
        const catName = data.product.mapped_category || "Товары для дома";
        setMessage(`✅ Товар успешно перенесён на Wildberries!\n🗺️ Категория автоматически определена как: "${catName}"`);
        loadData();
      } else {
        setMessage('❌ Ошибка миграции: ' + (data.detail || 'неизвестно'));
      }
    } catch (error) {
      setMessage('❌ Ошибка соединения с сервером');
    }
    setLoading(false);
  };

  const getStatusBadge = (status) => {
    const styles = { pending: 'badge-pending', success: 'badge-success', error: 'badge-error', processing: 'badge-processing' };
    const labels = { pending: 'Ожидает', success: 'Успешно', error: 'Ошибка', processing: 'В процессе' };
    return <span className={`badge ${styles[status]}`}>{labels[status]}</span>;
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>🔄 Marketplace Migrator</h1>
        <p>Перенос карточек товаров между маркетплейсами</p>
      </header>

      {message && (
        <div className={`alert ${message.includes('✅') ? 'alert-success' : 'alert-error'}`}>
          {message}
          <button onClick={() => setMessage('')} className="alert-close">✕</button>
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Всего товаров</div>
          <div className="stat-value">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Ожидают миграции</div>
          <div className="stat-value" style={{ color: '#f59e0b' }}>{stats.pending}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Успешно перенесено</div>
          <div className="stat-value" style={{ color: '#10b981' }}>{stats.success}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Ошибки</div>
          <div className="stat-value" style={{ color: '#ef4444' }}>{stats.error}</div>
        </div>
      </div>

      <div className="actions-panel">
        <button className="btn btn-primary" onClick={() => setShowImportModal(true)}>
          📥 Импортировать товары
        </button>
        <button className="btn btn-secondary" onClick={() => alert('Массовая миграция — в разработке')}>
          🔄 Запустить миграцию
        </button>
        <button className="btn btn-outline" onClick={() => alert('Настройки API — в разработке')}>
          ⚙️ Настройки API
        </button>
      </div>

      <div className="table-container">
        <h2>Список товаров</h2>
        {products.length === 0 ? (
          <p className="empty-state">Нет товаров. Нажмите "Импортировать товары" для начала.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Название</th>
                <th>Источник</th>
                <th>Цена</th>
                <th>Фото</th>
                <th>Статус</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <tr key={product.id}>
                  <td>{product.id}</td>
                  <td className="product-name">{product.name}</td>
                  <td>{product.source}</td>
                  <td>{product.price} ₽</td>
                  <td>{product.photos_count} шт.</td>
                  <td>{getStatusBadge(product.status)}</td>
                  <td>
                    <button 
                      className="btn btn-sm btn-primary"
                      onClick={() => handleMigrate(product.id)}
                      disabled={loading}
                    >
                      Перенести
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showImportModal && (
        <div className="modal-overlay" onClick={() => setShowImportModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>📥 Импорт товаров с Ozon</h2>
            <p className="modal-hint">
              Введите ключи Ozon Seller API в формате <b>CLIENT_ID:API_KEY</b>. 
              Для тестового режима введите любые короткие значения (например, <b>test:test</b>).
            </p>
            
            <label className="form-label">Ключ авторизации (Client-Id:Api-Key)</label>
            <input 
              className="form-input"
              type="text" 
              value={authKey}
              onChange={(e) => setAuthKey(e.target.value)}
              placeholder="12345678:a0b1c2d3-e4f5-6789-0123"
            />
            
            <div className="modal-actions">
              <button className="btn btn-outline" onClick={() => setShowImportModal(false)}>
                Отмена
              </button>
              <button className="btn btn-primary" onClick={handleImport} disabled={loading}>
                {loading ? '⏳ Загрузка...' : '✅ Импортировать'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;