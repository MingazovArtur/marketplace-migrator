import React, { useState, useEffect } from 'react';
import { api } from './api';
import './App.css';

const PLATFORMS = [
  { id: 'ozon', name: 'Ozon', color: '#005bff', logoText: 'O' },
  { id: 'wildberries', name: 'Wildberries', color: '#cb11ab', logoText: 'WB' },
  { id: 'yandex', name: 'Яндекс Маркет', color: '#fc3f1d', logoText: 'Я' }
];

function App() {
  const [stats, setStats] = useState({ total: 0, pending: 0, success: 0, error: 0 });
  const [products, setProducts] = useState([]);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showMigrateModal, setShowMigrateModal] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState('ozon');
  const [selectedMigratePlatform, setSelectedMigratePlatform] = useState('wildberries');
  const [currentProductId, setCurrentProductId] = useState(null);
  const [authKey, setAuthKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [statsData, productsData] = await Promise.all([api.getStats(), api.getProducts()]);
      setStats(statsData);
      setProducts(productsData.products || []);
    } catch (error) {
      setMessage('❌ Не удалось подключиться к бэкенду');
    }
  };

  const validateAuthKey = (key) => {
    if (!key.trim()) return 'Ключ авторизации обязателен';
    if (key.length < 3) return 'Ключ слишком короткий';
    return null;
  };

  const getPlaceholder = () => {
    const placeholders = {
      ozon: 'test:test',
      wildberries: 'mock_wb_key',
      yandex: 'test:test'
    };
    return placeholders[selectedPlatform] || 'ключ';
  };

  const handleImport = async () => {
    const error = validateAuthKey(authKey);
    if (error) { setMessage(`❌ ${error}`); return; }

    const fullKey = `${selectedPlatform}:${authKey}`;

    setLoading(true);
    setMessage('');
    try {
      const data = await api.importProducts(fullKey);
      if (data.success) {
        setMessage(`✅ Импортировано ${data.imported} товаров с ${data.platform_name}${data.is_mock ? ' (тест)' : ''}`);
        setAuthKey('');
        setShowImportModal(false);
        loadData();
      } else {
        setMessage('❌ Ошибка импорта: ' + (data.detail || 'неизвестно'));
      }
    } catch (error) {
      setMessage('❌ Ошибка соединения с сервером');
    }
    setLoading(false);
  };

  // ✅ Функция открытия модалки миграции
  const handleMigrate = (productId) => {
    setCurrentProductId(productId);
    setSelectedMigratePlatform('wildberries');
    setShowMigrateModal(true);
  };

  // ✅ Функция подтверждения миграции
  const handleMigrateConfirm = async () => {
    if (!currentProductId) return;

    setLoading(true);
    setMessage("⏳ Идет перенос товара...");
    setShowMigrateModal(false);

    try {
      const data = await api.migrateProduct(currentProductId, selectedMigratePlatform);
      if (data.success) {
        const catName = data.target_category?.name || "Неизвестно";
        const platformName = PLATFORMS.find(p => p.id === selectedMigratePlatform)?.name || selectedMigratePlatform;
        setMessage(`✅ Товар перенесён на ${platformName}!\n🗺️ Категория: "${catName}"`);
        loadData();
      } else {
        setMessage('❌ Ошибка миграции');
      }
    } catch (error) {
      setMessage('❌ Ошибка соединения');
    }
    setLoading(false);
    setCurrentProductId(null);
  };

  const getStatusBadge = (status) => {
    const styles = {
      pending: 'badge-pending',
      success: 'badge-success',
      error: 'badge-error',
      processing: 'badge-processing'
    };
    const labels = {
      pending: 'Ожидает',
      success: 'Успешно',
      error: 'Ошибка',
      processing: 'В процессе'
    };
    return <span className={`badge ${styles[status]}`}>{labels[status]}</span>;
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>
          🔄 Marketplace Migrator
          <span style={{ fontSize: '0.5em', color: '#10b981' }}>v2.1</span>
        </h1>
        <p>Универсальный перенос карточек между Ozon, Wildberries и Яндекс Маркет</p>
      </header>

      {message && (
        <div className={`alert ${message.includes('✅') ? 'alert-success' : 'alert-error'}`}>
          <div>
            {message.split('\n').map((line, i) => <div key={i}>{line}</div>)}
          </div>
          <button onClick={() => setMessage('')} className="alert-close">✕</button>
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Всего товаров</div>
          <div className="stat-value">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Ожидают</div>
          <div className="stat-value" style={{ color: '#f59e0b' }}>{stats.pending}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Успешно</div>
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
                    {product.status === 'success' ? (
                      <span className="badge badge-success">✅ Готово</span>
                    ) : (
                      <button
                        className="btn btn-sm btn-primary"
                        onClick={() => handleMigrate(product.id)}
                        disabled={loading}
                      >
                        Перенести
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ===== МОДАЛКА ИМПОРТА ===== */}
      {showImportModal && (
        <div className="modal-overlay" onClick={() => setShowImportModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>📥 Импорт товаров</h2>
              <button className="close-btn" onClick={() => setShowImportModal(false)}></button>
            </div>

            <label className="form-label">Выберите источник:</label>
            <div className="platform-selector">
              {PLATFORMS.map(p => (
                <button
                  key={p.id}
                  data-platform={p.id}
                  className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => {
                    setSelectedPlatform(p.id);
                    setAuthKey('');
                  }}
                >
                  <div
                    className="platform-logo"
                    style={{
                      backgroundColor: selectedPlatform === p.id ? p.color : '#f1f5f9',
                      color: selectedPlatform === p.id ? 'white' : '#64748b'
                    }}
                  >
                    {p.logoText}
                  </div>
                  <span>{p.name}</span>
                </button>
              ))}
            </div>

            <div className="modal-hint-box">
              <span className="hint-icon">💡</span>
              <p>
                Для тестирования введите <b>test:test</b> (или <b>mock_wb_key</b> для WB).
                Система загрузит демо-товары.
              </p>
            </div>

            <label className="form-label">Ключ авторизации</label>
            <input
              className={`form-input ${authKey && validateAuthKey(authKey) ? 'input-error' : ''}`}
              type="text"
              value={authKey}
              onChange={(e) => setAuthKey(e.target.value)}
              placeholder={getPlaceholder()}
            />
            {authKey && validateAuthKey(authKey) && (
              <div className="input-error-message">{validateAuthKey(authKey)}</div>
            )}

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

      {/* ===== МОДАЛКА МИГРАЦИИ ===== */}
{showMigrateModal && (
  <div className="modal-overlay" onClick={() => setShowMigrateModal(false)}>
    <div className="modal modal-small" onClick={(e) => e.stopPropagation()}>
      <div className="modal-header">
        <h2>🔄 Перенос товара</h2>
        <button className="close-btn" onClick={() => setShowMigrateModal(false)}></button>
      </div>

      <p className="modal-text">Выберите целевую платформу:</p>

      <div className="platform-selector">
        {PLATFORMS
          .filter(p => {
            // Определяем источник товара по его полю source
            const product = products.find(prod => prod.id === currentProductId);
            const sourcePlatform = product?.source?.toLowerCase() || '';
            
            // Исключаем текущую платформу товара
            if (sourcePlatform.includes('ozon') && !sourcePlatform.includes('→')) {
              return p.id !== 'ozon';
            }
            if (sourcePlatform.includes('wildberries') || sourcePlatform.includes('wb')) {
              return p.id !== 'wildberries';
            }
            if (sourcePlatform.includes('яндекс') || sourcePlatform.includes('yandex')) {
              return p.id !== 'yandex';
            }
            
            // Если товар уже был перенесен (есть стрелка →), берем последнюю платформу
            if (sourcePlatform.includes('→')) {
              const parts = sourcePlatform.split('→');
              const lastPlatform = parts[parts.length - 1].trim().toLowerCase();
              if (lastPlatform.includes('ozon')) return p.id !== 'ozon';
              if (lastPlatform.includes('wildberries') || lastPlatform.includes('wb')) return p.id !== 'wildberries';
              if (lastPlatform.includes('яндекс') || lastPlatform.includes('yandex')) return p.id !== 'yandex';
            }
            
            return true;
          })
          .map(p => (
            <button
              key={p.id}
              data-platform={p.id}
              className={`platform-btn ${selectedMigratePlatform === p.id ? 'platform-btn-active' : ''}`}
              onClick={() => setSelectedMigratePlatform(p.id)}
            >
              <div
                className="platform-logo"
                style={{
                  backgroundColor: selectedMigratePlatform === p.id ? p.color : '#f1f5f9',
                  color: selectedMigratePlatform === p.id ? 'white' : '#64748b'
                }}
              >
                {p.logoText}
              </div>
              <span>{p.name}</span>
            </button>
          ))}
      </div>

      <div className="modal-hint-box">
        <span className="hint-icon">💡</span>
        <p>Система автоматически определит категорию и перенесёт товар на выбранную площадку.</p>
      </div>

      <div className="modal-actions">
        <button className="btn btn-outline" onClick={() => setShowMigrateModal(false)}>
          Отмена
        </button>
        <button className="btn btn-primary" onClick={handleMigrateConfirm} disabled={loading}>
          {loading ? '⏳ Перенос...' : '✅ Перенести'}
        </button>
      </div>
    </div>
  </div>
)}
    </div>
  );
}

export default App;