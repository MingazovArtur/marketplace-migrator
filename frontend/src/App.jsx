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
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const [showImportModal, setShowImportModal] = useState(false);
  const [showMigrateModal, setShowMigrateModal] = useState(false);
  const [showBatchModal, setShowBatchModal] = useState(false);

  const [selectedPlatform, setSelectedPlatform] = useState('ozon');
  const [importMethod, setImportMethod] = useState('key');
  const [authKey, setAuthKey] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  const [selectedMigratePlatform, setSelectedMigratePlatform] = useState('wildberries');
  const [currentProductId, setCurrentProductId] = useState(null);
  const [previewData, setPreviewData] = useState(null);

  const [selectedProductIds, setSelectedProductIds] = useState([]);
  const [batchTaskId, setBatchTaskId] = useState(null);
  const [batchProgress, setBatchProgress] = useState({
    current: 0, total: 0, percent: 0, status: 'pending', success: 0, errors: 0
  });
  const [batchCompleted, setBatchCompleted] = useState(false);

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
    const fullKey = authKey.includes(':') && authKey.split(':')[0] === selectedPlatform ? authKey : `${selectedPlatform}:${authKey}`;

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
    if (!selectedFile) { setMessage('❌ Пожалуйста, выберите файл для загрузки'); return; }
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

  const handleMigrate = (productId) => {
    const product = products.find(p => p.id === productId);
    const source = product?.source?.toLowerCase() || '';
    
    const detectPlatform = (sourceStr) => {
      if (sourceStr.includes('→')) {
        const lastPart = sourceStr.split('→').pop().trim();
        if (lastPart.includes('ozon')) return 'ozon';
        if (lastPart.includes('wildberries') || lastPart.includes('wb')) return 'wildberries';
        if (lastPart.includes('яндекс') || lastPart.includes('yandex')) return 'yandex';
      }
      if (sourceStr.includes('ozon')) return 'ozon';
      if (sourceStr.includes('wildberries') || sourceStr.includes('wb')) return 'wildberries';
      if (sourceStr.includes('яндекс') || sourceStr.includes('yandex')) return 'yandex';
      return null;
    };
    
    const currentPlatform = detectPlatform(source);
    const availableTargets = PLATFORMS.filter(p => p.id !== currentPlatform);

    if (availableTargets.length === 0) {
      setMessage('⚠️ Товар уже перенесен на все доступные платформы');
      return;
    }

    setSelectedMigratePlatform(availableTargets[0].id);
    setCurrentProductId(productId);
    setPreviewData(null);
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
    
    const editedData = previewData ? {
      name: previewData.target.name,
      price: previewData.target.price,
      category: previewData.target.category
    } : null;

    try {
      const data = await api.migrateProduct(currentProductId, selectedMigratePlatform, editedData);
      if (data.success) {
        const platformName = PLATFORMS.find(p => p.id === selectedMigratePlatform)?.name;
        setMessage(`✅ Товар успешно перенесён на ${platformName}!`);
        loadData();
      }
    } catch (error) {
      setMessage('❌ ' + error.message);
    }
    setLoading(false);
    setCurrentProductId(null);
    setPreviewData(null);
  };

  const toggleProductSelection = (productId) => {
    setSelectedProductIds(prev => prev.includes(productId) ? prev.filter(id => id !== productId) : [...prev, productId]);
  };

  const toggleSelectAll = () => {
    if (selectedProductIds.length === products.length) {
      setSelectedProductIds([]);
    } else {
      setSelectedProductIds(products.map(p => p.id));
    }
  };

  const handleBatchMigrate = () => {
    if (selectedProductIds.length === 0) { setMessage('⚠️ Выберите хотя бы один товар'); return; }
    setShowBatchModal(true);
    setBatchCompleted(false);
    setBatchTaskId(null);
    setBatchProgress({ current: 0, total: selectedProductIds.length, percent: 0, status: 'pending', success: 0, errors: 0 });
  };

  const startBatchMigration = async () => {
    setLoading(true);
    try {
      const data = await api.migrateBatch(selectedProductIds, selectedMigratePlatform);
      setBatchTaskId(data.task_id);
      pollProgress(data.task_id);
    } catch (error) {
      setMessage('❌ ' + error.message);
      setShowBatchModal(false);
    }
    setLoading(false);
  };

  const pollProgress = (taskId) => {
    const interval = setInterval(async () => {
      try {
        const progress = await api.getTaskProgress(taskId);
        setBatchProgress(progress);
        if (progress.status === 'completed' || progress.status === 'error') {
          clearInterval(interval);
          setBatchCompleted(true);
          setSelectedProductIds([]);
        }
      } catch (error) {
        clearInterval(interval);
        setMessage('❌ Ошибка получения прогресса');
      }
    }, 1000);
  };

  const closeBatchModal = () => {
    setShowBatchModal(false);
    setBatchTaskId(null);
    setBatchCompleted(false);
    loadData();
  };

  const handleExport = async () => {
    if (stats.total === 0) { setMessage('⚠️ Нет товаров для экспорта.'); return; }
    try {
      await api.exportReport();
      setMessage('✅ Отчет успешно скачан!');
    } catch (error) {
      setMessage('❌ Ошибка при скачивании отчета: ' + error.message);
    }
  };

  const getStatusBadge = (status) => {
    const styles = { pending: 'badge-pending', success: 'badge-success', error: 'badge-error', processing: 'badge-processing' };
    const labels = { pending: 'Ожидает', success: 'Успешно', error: 'Ошибка', processing: 'В процессе' };
    return <span className={`badge ${styles[status]}`}>{labels[status]}</span>;
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>🔄 Marketplace Migrator <span style={{ fontSize: '0.5em', color: '#10b981' }}>v3.1</span></h1>
        <p>Универсальный перенос карточек: Ozon, Wildberries, Яндекс Маркет</p>
      </header>

      {message && (
        <div className={`alert ${message.includes('✅') ? 'alert-success' : 'alert-error'}`}>
          <div>{message.split('\n').map((line, i) => <div key={i}>{line}</div>)}</div>
          <button onClick={() => setMessage('')} className="alert-close">✕</button>
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card"><div className="stat-label">Всего товаров</div><div className="stat-value">{stats.total}</div></div>
        <div className="stat-card"><div className="stat-label">Ожидают</div><div className="stat-value" style={{ color: '#f59e0b' }}>{stats.pending}</div></div>
        <div className="stat-card"><div className="stat-label">Успешно</div><div className="stat-value" style={{ color: '#10b981' }}>{stats.success}</div></div>
        <div className="stat-card"><div className="stat-label">Ошибки</div><div className="stat-value" style={{ color: '#ef4444' }}>{stats.error}</div></div>
      </div>

      <div className="actions-panel">
        <button className="btn btn-primary" onClick={() => setShowImportModal(true)}>📥 Импортировать товары</button>
        <button className="btn btn-secondary" onClick={handleBatchMigrate} disabled={selectedProductIds.length === 0 || loading}>
          🔄 Перенести выбранные ({selectedProductIds.length})
        </button>
        <button className="btn btn-secondary" onClick={handleExport} disabled={stats.total === 0}>📊 Скачать отчет (Excel)</button>
      </div>

      <div className="table-container">
        <h2>Список товаров</h2>
        {products.length === 0 ? (
          <p className="empty-state">Нет товаров. Нажмите "Импортировать товары" для начала.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{width: '40px'}}><input type="checkbox" checked={selectedProductIds.length === products.length && products.length > 0} onChange={toggleSelectAll} className="checkbox-input" /></th>
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
                <tr key={product.id} className={selectedProductIds.includes(product.id) ? 'row-selected' : ''}>
                  <td><input type="checkbox" checked={selectedProductIds.includes(product.id)} onChange={() => toggleProductSelection(product.id)} className="checkbox-input" /></td>
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
                      <button className="btn btn-sm btn-primary" onClick={() => handleMigrate(product.id)} disabled={loading}>Перенести</button>
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
            <div className="modal-header"><h2>📥 Импорт товаров</h2><button className="close-btn" onClick={() => setShowImportModal(false)}>✕</button></div>
            <label className="form-label">1. Выберите источник:</label>
            <div className="platform-selector">
              {PLATFORMS.map(p => (
                <button key={p.id} data-platform={p.id} className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`} onClick={() => { setSelectedPlatform(p.id); setAuthKey(''); setSelectedFile(null); }}>
                  <div className="platform-logo" style={{ backgroundColor: selectedPlatform === p.id ? p.color : '#f1f5f9', color: selectedPlatform === p.id ? 'white' : '#64748b' }}>{p.logoText}</div>
                  <span>{p.name}</span>
                </button>
              ))}
            </div>
            <label className="form-label">2. Выберите способ:</label>
            <div className="import-method-toggle">
              <button className={`toggle-btn ${importMethod === 'key' ? 'active' : ''}`} onClick={() => setImportMethod('key')}>🔑 По API / Ключу / YML</button>
              <button className={`toggle-btn ${importMethod === 'file' ? 'active' : ''}`} onClick={() => setImportMethod('file')}>📁 Из Excel / CSV</button>
            </div>
            {importMethod === 'key' ? (
              <>
                <div className="modal-hint-box"><span className="hint-icon">💡</span><p>{getInputHint()}</p></div>
                <label className="form-label">Ключ или URL</label>
                <input className={`form-input ${authKey && validateAuthKey(authKey) ? 'input-error' : ''}`} type="text" value={authKey} onChange={(e) => setAuthKey(e.target.value)} placeholder={selectedPlatform === 'yandex' ? 'test:test или https://site.ru/yml.xml' : 'test:test'} />
                {authKey && validateAuthKey(authKey) && <div className="input-error-message">{validateAuthKey(authKey)}</div>}
                <div className="modal-actions">
                  <button className="btn btn-outline" onClick={() => setShowImportModal(false)}>Отмена</button>
                  <button className="btn btn-primary" onClick={handleImport} disabled={loading}>{loading ? '⏳ Загрузка...' : '✅ Импортировать'}</button>
                </div>
              </>
            ) : (
              <>
                <div className="modal-hint-box"><span className="hint-icon">📊</span><p>Загрузите выгрузку товаров из личного кабинета {PLATFORMS.find(p => p.id === selectedPlatform)?.name}.</p></div>
                <label className="form-label">Выберите файл (.xlsx или .csv)</label>
                <input type="file" accept=".xlsx,.csv" onChange={(e) => setSelectedFile(e.target.files[0])} className="form-input" />
                {selectedFile && <div className="selected-file-info">📎 Выбран: <b>{selectedFile.name}</b> ({(selectedFile.size / 1024).toFixed(1)} KB)</div>}
                <div className="modal-actions">
                  <button className="btn btn-outline" onClick={() => {setShowImportModal(false); setSelectedFile(null);}}>Отмена</button>
                  <button className="btn btn-primary" onClick={handleFileImport} disabled={loading || !selectedFile}>{loading ? '⏳ Обработка...' : '✅ Загрузить и импортировать'}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ===== МОДАЛЬНОЕ ОКНО ОДИНОЧНОЙ МИГРАЦИИ ===== */}
      {showMigrateModal && (
        <div className="modal-overlay" onClick={() => setShowMigrateModal(false)}>
          <div className="modal modal-preview" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header"><h2>🔄 Перенос товара</h2><button className="close-btn" onClick={() => {setShowMigrateModal(false); setPreviewData(null);}}>✕</button></div>
                        {!previewData ? (
              <>
                <p className="modal-text">Выберите целевую платформу:</p>
                
                <div className="platform-selector">
                  {PLATFORMS.filter(p => {
                    // Получаем товар
                    const product = products.find(prod => prod.id === currentProductId);
                    const source = product?.source?.toLowerCase() || '';
                    
                    // Функция определения платформы (такая же как в handleMigrate)
                    const detectPlatform = (sourceStr) => {
                      if (sourceStr.includes('→')) {
                        const lastPart = sourceStr.split('→').pop().trim();
                        if (lastPart.includes('ozon')) return 'ozon';
                        if (lastPart.includes('wildberries') || lastPart.includes('wb')) return 'wildberries';
                        if (lastPart.includes('яндекс') || lastPart.includes('yandex')) return 'yandex';
                      }
                      if (sourceStr.includes('ozon')) return 'ozon';
                      if (sourceStr.includes('wildberries') || sourceStr.includes('wb')) return 'wildberries';
                      if (sourceStr.includes('яндекс') || sourceStr.includes('yandex')) return 'yandex';
                      return null;
                    };
                    
                    const currentPlatform = detectPlatform(source);
                    
                    // Исключаем текущую платформу
                    return p.id !== currentPlatform;
                  }).map(p => (
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
                    {loading ? '⏳ Загрузка...' : '👁️ Показать предпросмотр'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="preview-comparison">
                  <div className="preview-card original">
                    <h3>📦 Было (Источник)</h3>
                    <div className="preview-row"><span className="label">Название:</span><span className="value">{previewData.original.name}</span></div>
                    <div className="preview-row"><span className="label">Цена:</span><span className="value price">{previewData.original.price} ₽</span></div>
                    <div className="preview-row"><span className="label">Категория:</span><span className="value">{previewData.original.category}</span></div>
                  </div>
                  <div className="preview-arrow">➜</div>
                  <div className="preview-card target editable">
                    <h3>🎯 Станет ({PLATFORMS.find(p => p.id === selectedMigratePlatform)?.name})</h3>
                    <div className="preview-row editable-row">
                      <span className="label">Название:</span>
                      <textarea className="editable-input" value={previewData.target.name} onChange={(e) => setPreviewData({...previewData, target: {...previewData.target, name: e.target.value}})} rows={3} />
                    </div>
                    <div className="preview-row editable-row">
                      <span className="label">Цена:</span>
                      <div className="price-input-wrapper">
                        <input type="number" className="editable-input price-input" value={previewData.target.price} onChange={(e) => {
                          const newPrice = parseFloat(e.target.value) || 0;
                          const originalPrice = previewData.original.price;
                          const percentChange = ((newPrice - originalPrice) / originalPrice * 100).toFixed(0);
                          setPreviewData({...previewData, target: {...previewData.target, price: newPrice, priceChangePercent: percentChange}});
                        }} step="0.01" min="0" />
                        {previewData.target.priceChangePercent > 0 && <span className="badge badge-success" style={{fontSize: '0.7em', marginLeft: '5px'}}>+{previewData.target.priceChangePercent}%</span>}
                      </div>
                    </div>
                    <div className="preview-row editable-row">
                      <span className="label">Категория:</span>
                      <input type="text" className="editable-input" value={previewData.target.category} onChange={(e) => setPreviewData({...previewData, target: {...previewData.target, category: e.target.value}})} />
                    </div>
                  </div>
                </div>
                <div className="modal-hint-box" style={{marginTop: '1.5rem'}}><span className="hint-icon">✏️</span><p>Вы можете изменить данные перед переносом. Все изменения будут применены к новой карточке товара.</p></div>
                <div className="modal-actions">
                  <button className="btn btn-outline" onClick={() => setPreviewData(null)}>← Выбрать другую платформу</button>
                  <button className="btn btn-primary" onClick={handleMigrateConfirm} disabled={loading}>{loading ? '⏳ Перенос...' : '✅ Подтвердить и перенести'}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ===== МОДАЛЬНОЕ ОКНО ПАКЕТНОЙ МИГРАЦИИ ===== */}
      {showBatchModal && (
        <div className="modal-overlay" onClick={() => !batchCompleted && setShowBatchModal(false)}>
          <div className="modal modal-batch" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header"><h2>🔄 Пакетная миграция</h2>{batchCompleted && <button className="close-btn" onClick={closeBatchModal}>✕</button>}</div>
            {!batchTaskId ? (
              <>
                <p className="modal-text">Выбрано товаров: <b>{selectedProductIds.length}</b>. Выберите целевую платформу:</p>
                <div className="platform-selector">
                  {PLATFORMS.map(p => (
                    <button key={p.id} data-platform={p.id} className={`platform-btn ${selectedMigratePlatform === p.id ? 'platform-btn-active' : ''}`} onClick={() => setSelectedMigratePlatform(p.id)}>
                      <div className="platform-logo" style={{ backgroundColor: selectedMigratePlatform === p.id ? p.color : '#f1f5f9', color: selectedMigratePlatform === p.id ? 'white' : '#64748b' }}>{p.logoText}</div>
                      <span>{p.name}</span>
                    </button>
                  ))}
                </div>
                <div className="modal-hint-box"><span className="hint-icon">⚡</span><p>Миграция будет выполняться в фоновом режиме. Вы сможете наблюдать за прогрессом в реальном времени.</p></div>
                <div className="modal-actions">
                  <button className="btn btn-outline" onClick={() => setShowBatchModal(false)}>Отмена</button>
                  <button className="btn btn-primary" onClick={startBatchMigration} disabled={loading}>🚀 Запустить миграцию</button>
                </div>
              </>
            ) : (
              <>
                <div className="batch-progress-container">
                  <div className="progress-stats">
                    <div className="stat-item"><div className="stat-label">Всего</div><div className="stat-value">{batchProgress.total}</div></div>
                    <div className="stat-item"><div className="stat-label">Обработано</div><div className="stat-value">{batchProgress.current}</div></div>
                    <div className="stat-item success"><div className="stat-label">Успешно</div><div className="stat-value">{batchProgress.success || 0}</div></div>
                    <div className="stat-item error"><div className="stat-label">Ошибок</div><div className="stat-value">{batchProgress.errors || 0}</div></div>
                  </div>
                  <div className="progress-bar-wrapper">
                    <div className="progress-bar-fill" style={{ width: `${batchProgress.percent}%` }}></div>
                    <div className="progress-bar-text">{batchProgress.percent}%</div>
                  </div>
                  <div className="progress-status">
                    {batchProgress.status === 'pending' && <span>⏳ Ожидание запуска...</span>}
                    {batchProgress.status === 'processing' && <span>⚙️ Обработка товаров...</span>}
                    {batchProgress.status === 'completed' && <span className="success-text">✅ Миграция завершена! Успешно: {batchProgress.success}, Ошибок: {batchProgress.errors}</span>}
                    {batchProgress.status === 'error' && <span className="error-text">❌ Произошла ошибка</span>}
                  </div>
                  {batchProgress.error_details && batchProgress.error_details.length > 0 && (
                    <div className="error-details">
                      <h4>Детали ошибок:</h4>
                      <ul>{batchProgress.error_details.map((err, i) => <li key={i}>Товар #{err.id}: {err.error}</li>)}</ul>
                    </div>
                  )}
                </div>
                {batchCompleted && (
                  <div className="modal-actions">
                    <button className="btn btn-primary" onClick={closeBatchModal}>✅ Закрыть и обновить таблицу</button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;