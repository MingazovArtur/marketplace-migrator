import React, { useState } from 'react';
import Modal from '../common/Modal';
import Button from '../common/Button';
import { PLATFORMS } from '../../utils/platformUtils';

const ImportModal = ({ isOpen, onClose, onImport, onFileImport, loading }) => {
  const [selectedPlatform, setSelectedPlatform] = useState('ozon');
  const [importMethod, setImportMethod] = useState('key');
  const [authKey, setAuthKey] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

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
    if (error) {
      alert(`❌ ${error}`);
      return;
    }

    const keyStr = String(authKey).trim();
    const platformStr = String(selectedPlatform).toLowerCase();
    const fullKey = keyStr.includes(':') && keyStr.split(':')[0].toLowerCase() === platformStr
      ? keyStr
      : `${platformStr}:${keyStr}`;

    onImport(fullKey);
  };

  const handleFileImport = () => {
    if (!selectedFile) {
      alert(' Пожалуйста, выберите файл для загрузки');
      return;
    }
    onFileImport(selectedPlatform, selectedFile);
  };

  const handleClose = () => {
    setAuthKey('');
    setSelectedFile(null);
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="📥 Импорт товаров">
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
            <Button variant="outline" onClick={handleClose}>Отмена</Button>
            <Button onClick={handleImport} disabled={loading}>
              {loading ? '⏳ Загрузка...' : '✅ Импортировать'}
            </Button>
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
            <Button variant="outline" onClick={handleClose}>Отмена</Button>
            <Button onClick={handleFileImport} disabled={loading || !selectedFile}>
              {loading ? '⏳ Обработка...' : '✅ Загрузить и импортировать'}
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
};

export default ImportModal;