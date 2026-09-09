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
  
  const [importMethod, setImportMethod] = useState('key');
  const [authKey, setAuthKey] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  
  const [previewData, setPreviewData] = useState(null);
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
    if (!key.trim()) return 'Поле обязательно для заполнения';
    if (key.length < 3) return 'Слишком короткое значение';
    return null;
  };

  const getInputHint = () => {
    const hints = {
      ozon: 'Для теста: test:test. Для реального API: CLIENT_ID:API_KEY',
      wildberries: 'Для теста: mock_wb_key (импорт только в демо-режиме)',
      yandex: 'Для теста: test:test. Для API: campaign_id:oauth_token. Или URL YML-фида.'
    };
    return hints[selectedPlatform] || '';
  };

  const handleImport = async () => {
    const error = validateAuthKey(authKey);
    if (error) { setMessage(`❌ ${error}`); return; }

    const fullKey = authKey.includes(':') && authKey.split(':')[0] === selectedPlatform 
      ? authKey 
      : `${selectedPlatform}:${authKey}`;

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
      setMessage('❌ ' + error.message);
    }
    setLoading(false);
  };

  const handleFileImport = async () => {
    if (!selectedFile) {
      setMessage('❌ Пожалуйста, выберите файл для загрузки');
      return;
    }
    
    setLoading(true);
    setMessage('');
    try {
      const data = await api.importFromFile(selectedPlatform, selectedFile);
      if (data.success) {
        setMessage(`✅ ${data.message}`);
        setSelectedFile(null);
        setShowImportModal(false);
        loadData();
      }
    } catch (error) {
      setMessage('❌ ' + error.message);
    }
    setLoading(false);
  };

  const handleMigrate = async (productId) => {
  const product = products.find(p => p.id === productId);
  const source = product?.source?.toLowerCase() || '';
  
  // Определяем доступные целевые платформы (исключая текущую)
  const availableTargets = PLATFORMS.filter(p => {
    if (source.includes('→')) {
      const lastPlatform = source.split('→').pop().trim().toLowerCase();
      return !lastPlatform.includes(p.id);
    }
    return !source.includes(p.id);
  });

  if (availableTargets.length === 0) {
    setMessage('⚠️ Товар уже перенесен на все доступные платформы');
    return;
  }

  // По умолчанию выбираем первую доступную
  setSelectedMigratePlatform(availableTargets[0].id);
  setCurrentProductId(productId);
  setPreviewData(null); // Сбрасываем старый предпросмотр
  
  // Открываем модалку БЕЗ предпросмотра (пользователь сначала выберет платформу)
  setShowMigrateModal(true);
  };

  const loadPreview = async () => {
  if (!currentProductId) return;
  
  setLoading(true);
  try {
    const data = await api.previewMigration(currentProductId, selectedMigratePlatform);
    setPreviewData(data.preview);
  } catch (error) {
    setMessage('❌ Не удалось загрузить предпросмотр: ' + error.message);
    setPreviewData(null);
  }
  setLoading(false);
  };
  
  const handleMigrateConfirm = async () => {
    if (!currentProductId) return;

    setLoading(true);
    setMessage("⏳ Идет перенос товара...");
    setShowMigrateModal(false);
    setPreviewData(null);

    try {
      const data = await api.migrateProduct(currentProductId, selectedMigratePlatform);
      if (data.success) {
        const platformName = PLATFORMS.find(p => p.id === selectedMigratePlatform)?.name;
        setMessage(`✅ Товар успешно перенесён на ${platformName}!\n🗺️ Категория: "${data.target_category?.name}"`);
        loadData();
      }
    } catch (error) {
      setMessage('❌ ' + error.message);
    }
    setLoading(false);
    setCurrentProductId(null);
  };

  const handleExport = async () => {
    if (stats.total === 0) {
      setMessage('⚠️ Нет товаров для экспорта. Сначала импортируйте данные.');
      return;
    }
    try {
      await api.exportReport();
      setMessage('✅ Отчет успешно скачан!');
    } catch (error) {
      setMessage('❌ Ошибка при скачивании отчета: ' + error.message);
    }
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
          <span style={{ fontSize: '0.5em', color: '#10b981' }}>v2.2</span>
        </h1>
        <p>Универсальный перенос карточек: Ozon, Wildberries, Яндекс Маркет</p>
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
        <button className="btn btn-secondary" onClick={handleExport} disabled={stats.total === 0}>
          📊 Скачать отчет (Excel)
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
                  <td className="product-name" title={product.name}>{product.name}</td>
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

      {/* ===== МОДАЛЬНОЕ ОКНО ИМПОРТА ===== */}
      {showImportModal && (
        <div className="modal-overlay" onClick={() => setShowImportModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>📥 Импорт товаров</h2>
              <button className="close-btn" onClick={() => setShowImportModal(false)}>✕</button>
            </div>

            <label className="form-label">1. Выберите источник:</label>
            <div className="platform-selector">
              {PLATFORMS.map(p => (
                <button
                  key={p.id}
                  data-platform={p.id}
                  className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => {
                    setSelectedPlatform(p.id);
                    setAuthKey('');
                    setSelectedFile(null);
                  }}
                >
                  <div className="platform-logo" style={{
                    backgroundColor: selectedPlatform === p.id ? p.color : '#f1f5f9',
                    color: selectedPlatform === p.id ? 'white' : '#64748b'
                  }}>
                    {p.logoText}
                  </div>
                  <span>{p.name}</span>
                </button>
              ))}
            </div>

            <label className="form-label">2. Выберите способ:</label>
            <div className="import-method-toggle">
              <button 
                className={`toggle-btn ${importMethod === 'key' ? 'active' : ''}`}
                onClick={() => setImportMethod('key')}
              >
                🔑 По API / Ключу / YML
              </button>
              <button 
                className={`toggle-btn ${importMethod === 'file' ? 'active' : ''}`}
                onClick={() => setImportMethod('file')}
              >
                📁 Из Excel / CSV
              </button>
            </div>

            {importMethod === 'key' ? (
              <>
                <div className="modal-hint-box">
                  <span className="hint-icon">💡</span>
                  <p>{getInputHint()}</p>
                </div>
                <label className="form-label">Ключ или URL</label>
                <input 
                  className={`form-input ${authKey && validateAuthKey(authKey) ? 'input-error' : ''}`}
                  type="text" 
                  value={authKey} 
                  onChange={(e) => setAuthKey(e.target.value)}
                  placeholder={selectedPlatform === 'yandex' ? 'test:test или https://site.ru/yml.xml' : 'test:test'}
                />
                {authKey && validateAuthKey(authKey) && (
                  <div className="input-error-message">{validateAuthKey(authKey)}</div>
                )}
                <div className="modal-actions">
                  <button className="btn btn-outline" onClick={() => setShowImportModal(false)}>Отмена</button>
                  <button className="btn btn-primary" onClick={handleImport} disabled={loading}>
                    {loading ? '⏳ Загрузка...' : '✅ Импортировать'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="modal-hint-box">
                  <span className="hint-icon">📊</span>
                  <p>Загрузите выгрузку товаров из личного кабинета {PLATFORMS.find(p => p.id === selectedPlatform)?.name}.</p>
                </div>
                <label className="form-label">Выберите файл (.xlsx или .csv)</label>
                <input 
                  type="file" 
                  accept=".xlsx,.csv"
                  onChange={(e) => setSelectedFile(e.target.files[0])}
                  className="form-input"
                />
                {selectedFile && (
                  <div className="selected-file-info">
                    📎 Выбран: <b>{selectedFile.name}</b> ({(selectedFile.size / 1024).toFixed(1)} KB)
                  </div>
                )}
                <div className="modal-actions">
                  <button className="btn btn-outline" onClick={() => {setShowImportModal(false); setSelectedFile(null);}}>Отмена</button>
                  <button className="btn btn-primary" onClick={handleFileImport} disabled={loading || !selectedFile}>
                    {loading ? '⏳ Обработка...' : '✅ Загрузить и импортировать'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      
      {/* ===== МОДАЛЬНОЕ ОКНО МИГРАЦИИ С ВЫБОРОМ ПЛАТФОРМЫ ===== */}
      {showMigrateModal && (
  <div className="modal-overlay" onClick={() => setShowMigrateModal(false)}>
    <div className="modal modal-preview" onClick={(e) => e.stopPropagation()}>
      <div className="modal-header">
        <h2>🔄 Перенос товара</h2>
        <button className="close-btn" onClick={() => {setShowMigrateModal(false); setPreviewData(null);}}>✕</button>
      </div>

      {/* Шаг 1: Выбор целевой платформы */}
      {!previewData && (
        <>
          <p className="modal-text">Выберите целевую платформу:</p>
          
          <div className="platform-selector">
            {PLATFORMS
              .filter(p => {
                const product = products.find(prod => prod.id === currentProductId);
                const source = product?.source?.toLowerCase() || '';
                
                if (source.includes('→')) {
                  const lastPlatform = source.split('→').pop().trim().toLowerCase();
                  return !lastPlatform.includes(p.id);
                }
                return !source.includes(p.id);
              })
              .map(p => (
                <button
                  key={p.id}
                  data-platform={p.id}
                  className={`platform-btn ${selectedMigratePlatform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => setSelectedMigratePlatform(p.id)}
                >
                  <div className="platform-logo" style={{
                    backgroundColor: selectedMigratePlatform === p.id ? p.color : '#f1f5f9',
                    color: selectedMigratePlatform === p.id ? 'white' : '#64748b'
                  }}>
                    {p.logoText}
                  </div>
                  <span>{p.name}</span>
                </button>
              ))}
          </div>

          <div className="modal-actions">
            <button className="btn btn-outline" onClick={() => setShowMigrateModal(false)}>Отмена</button>
            <button className="btn btn-primary" onClick={loadPreview} disabled={loading}>
              {loading ? ' Загрузка...' : '👁️ Показать предпросмотр'}
            </button>
          </div>
        </>
      )}

      {/* Шаг 2: Предпросмотр после выбора платформы */}
      {previewData && (
        <>
          <div className="preview-comparison">
            <div className="preview-card original">
              <h3>📦 Было (Источник)</h3>
              <div className="preview-row">
                <span className="label">Название:</span>
                <span className="value">{previewData.original.name}</span>
              </div>
              <div className="preview-row">
                <span className="label">Цена:</span>
                <span className="value price">{previewData.original.price} ₽</span>
              </div>
              <div className="preview-row">
                <span className="label">Категория:</span>
                <span className="value">{previewData.original.category}</span>
              </div>
            </div>

            <div className="preview-arrow">➜</div>

            <div className="preview-card target">
              <h3>🎯 Станет ({PLATFORMS.find(p => p.id === selectedMigratePlatform)?.name})</h3>
              <div className="preview-row">
                <span className="label">Название:</span>
                <span className="value highlight">{previewData.target.name}</span>
              </div>
              <div className="preview-row">
                <span className="label">Цена:</span>
                <span className="value price highlight">
                  {previewData.target.price} ₽ 
                  {previewData.target.price > previewData.original.price && (
                    <span className="badge badge-success" style={{fontSize: '0.7em', marginLeft: '5px'}}>+15%</span>
                  )}
                </span>
              </div>
              <div className="preview-row">
                <span className="label">Категория:</span>
                <span className="value highlight">{previewData.target.category}</span>
              </div>
            </div>
          </div>

          <div className="modal-hint-box" style={{marginTop: '1.5rem'}}>
            <span className="hint-icon">🧠</span>
            <p>{previewData.mapping_reason}</p>
          </div>

          <div className="modal-actions">
            <button className="btn btn-outline" onClick={() => setPreviewData(null)}>
              ← Выбрать другую платформу
            </button>
            <button className="btn btn-primary" onClick={handleMigrateConfirm} disabled={loading}>
              {loading ? '⏳ Перенос...' : '✅ Подтвердить и перенести'}
            </button>
          </div>
        </>
      )}
    </div>
  </div>
      )}
    </div>
  );
}

export default App;