import React, { useState, useRef } from 'react';
import Button from '../common/Button';
import { PLATFORMS } from '../../utils/platformUtils';

const ImportModal = ({ isOpen, onClose, onImport, onFileImport, loading }) => {
  const [selectedPlatform, setSelectedPlatform] = useState('ozon');
  const [importMethod, setImportMethod] = useState('key');
  const [authKey, setAuthKey] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

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

  const handleImport = () => {
    const error = validateAuthKey(authKey);
    if (error) { alert(`❌ ${error}`); return; }
    const keyStr = String(authKey).trim();
    const platformStr = selectedPlatform.toLowerCase();
    const fullKey = keyStr.includes(':') && keyStr.split(':')[0].toLowerCase() === platformStr ? keyStr : `${platformStr}:${keyStr}`;
    onImport(fullKey);
  };

  const handleFileImport = () => {
    if (!selectedFile) { alert('⚠️ Выберите файл'); return; }
    onFileImport(selectedPlatform, selectedFile);
  };

  const handleClose = () => { setAuthKey(''); setSelectedFile(null); onClose(); };

  // Drag-and-Drop обработчики
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.xlsx') || file.name.endsWith('.csv'))) {
      setSelectedFile(file);
    } else {
      alert('⚠️ Поддерживаются только файлы .xlsx и .csv');
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) setSelectedFile(file);
  };

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">📥 Импорт товаров</h2>
          <button className="close-btn" onClick={handleClose}>✕</button>
        </div>

        <label className="form-label">1. Выберите источник:</label>
        <div className="platform-selector">
          {PLATFORMS.map(p => (
            <button
              key={p.id}
              className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`}
              onClick={() => { setSelectedPlatform(p.id); setAuthKey(''); setSelectedFile(null); }}
              data-platform={p.id}
            >
              <div className="platform-logo" style={{
                backgroundColor: selectedPlatform === p.id ? p.color : 'var(--bg-tertiary)',
                color: selectedPlatform === p.id ? 'white' : 'var(--text-muted)'
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
              <Button variant="outline" onClick={handleClose}>Отмена</Button>
              <Button onClick={handleImport} disabled={loading} loading={loading}>
                {loading ? 'Загрузка...' : '✅ Импортировать'}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="modal-hint-box">
              <span className="hint-icon">📊</span>
              <p>Загрузите выгрузку товаров из личного кабинета {PLATFORMS.find(p => p.id === selectedPlatform)?.name}.</p>
            </div>
            
            {/* Drag-and-Drop зона с pulse-анимацией */}
            <div
              className={`drop-zone ${isDragging ? 'dragging' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="drop-zone-icon"></div>
              <div className="drop-zone-text">
                {selectedFile ? (
                  <>
                    <strong>{selectedFile.name}</strong><br />
                    <small>{(selectedFile.size / 1024).toFixed(1)} KB</small>
                  </>
                ) : (
                  <>
                    Перетащите файл сюда или <strong>нажмите для выбора</strong><br />
                    <small>Поддерживаются .xlsx и .csv</small>
                  </>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.csv"
                onChange={handleFileSelect}
                style={{ display: 'none' }}
              />
            </div>
            
            <div className="modal-actions">
              <Button variant="outline" onClick={handleClose}>Отмена</Button>
              <Button onClick={handleFileImport} disabled={loading || !selectedFile} loading={loading}>
                {loading ? 'Обработка...' : '✅ Загрузить и импортировать'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ImportModal;