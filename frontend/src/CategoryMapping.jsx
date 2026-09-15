import React, { useState, useEffect } from 'react';
import './App.css';

const API_URL = 'http://localhost:8000/api';
const PLATFORMS = [
  { id: 'ozon', name: 'Ozon', color: '#005bff' },
  { id: 'wildberries', name: 'Wildberries', color: '#cb11ab' },
  { id: 'yandex', name: 'Яндекс Маркет', color: '#fc3f1d' }
];

function CategoryMapping({ onBack }) {
  const [sourcePlatform, setSourcePlatform] = useState('ozon');
  const [targetPlatform, setTargetPlatform] = useState('wildberries');
  const [sourceCategories, setSourceCategories] = useState([]);
  const [targetCategories, setTargetCategories] = useState([]);
  const [selectedSource, setSelectedSource] = useState(null);
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  
  // API ключи
  const [sourceApiKey, setSourceApiKey] = useState('');
  const [targetApiKey, setTargetApiKey] = useState('');
  const [showApiKeyInput, setShowApiKeyInput] = useState(false);

  useEffect(() => {
    loadCategories();
  }, [sourcePlatform, targetPlatform]);

  const loadCategories = async (useApiKey = false) => {
    setLoading(true);
    setMessage('');
    
    try {
      // Загружаем исходные категории
      let sourceUrl = `${API_URL}/categories/${sourcePlatform}`;
      if (useApiKey && sourceApiKey) {
        const res = await fetch(`${API_URL}/categories/${sourcePlatform}/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: sourceApiKey })
        });
        const data = await res.json();
        setSourceCategories(data.categories || []);
      } else {
        const res = await fetch(sourceUrl);
        const data = await res.json();
        setSourceCategories(data.categories || []);
      }
      
      // Загружаем целевые категории
      let targetUrl = `${API_URL}/categories/${targetPlatform}`;
      if (useApiKey && targetApiKey) {
        const res = await fetch(`${API_URL}/categories/${targetPlatform}/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: targetApiKey })
        });
        const data = await res.json();
        setTargetCategories(data.categories || []);
      } else {
        const res = await fetch(targetUrl);
        const data = await res.json();
        setTargetCategories(data.categories || []);
      }
      
      if (useApiKey) {
        setMessage('✅ Справочники обновлены из API');
      }
    } catch (error) {
      setMessage('❌ Ошибка загрузки категорий');
    }
    
    setLoading(false);
  };

  const handleSaveMapping = async () => {
    if (!selectedSource || !selectedTarget) {
      setMessage('⚠️ Выберите категории с обеих сторон');
      return;
    }
    
    try {
      const res = await fetch(
        `${API_URL}/category-mapping?source_platform=${sourcePlatform}&source_category_id=${selectedSource.id}&target_platform=${targetPlatform}&target_category_id=${selectedTarget.id}`,
        { method: 'POST' }
      );
      
      const data = await res.json();
      
      if (data.success) {
        setMessage(`✅ Маппинг сохранен: ${selectedSource.name} → ${selectedTarget.name}`);
        setMappings([...mappings, {
          source: selectedSource,
          target: selectedTarget
        }]);
        setSelectedSource(null);
        setSelectedTarget(null);
      } else {
        setMessage('❌ Ошибка сохранения маппинга');
      }
    } catch (error) {
      setMessage(' Ошибка соединения с сервером');
    }
  };

  return (
    <div className="category-mapping-container">
      <div className="mapping-header">
        <h2>🗺️ Настройка маппинга категорий</h2>
        <button className="btn btn-outline" onClick={onBack}>← Назад</button>
      </div>

      {message && (
        <div className={`alert ${message.includes('✅') ? 'alert-success' : 'alert-error'}`}>
          {message}
          <button onClick={() => setMessage('')} className="alert-close">✕</button>
        </div>
      )}

      {/* Настройки платформ */}
      <div className="mapping-platforms">
        <div className="platform-selector-group">
          <label>Источник:</label>
          <select 
            value={sourcePlatform} 
            onChange={(e) => setSourcePlatform(e.target.value)}
            className="form-input"
          >
            {PLATFORMS.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        
        <div className="mapping-arrow">➜</div>
        
        <div className="platform-selector-group">
          <label>Назначение:</label>
          <select 
            value={targetPlatform} 
            onChange={(e) => setTargetPlatform(e.target.value)}
            className="form-input"
          >
            {PLATFORMS.filter(p => p.id !== sourcePlatform).map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Кнопка обновления справочников */}
      <div className="mapping-actions">
        <button 
          className="btn btn-secondary"
          onClick={() => setShowApiKeyInput(!showApiKeyInput)}
        >
          🔑 {showApiKeyInput ? 'Скрыть' : 'Ввести'} API ключи
        </button>
        <button 
          className="btn btn-primary"
          onClick={() => loadCategories(true)}
          disabled={loading}
        >
          {loading ? ' Загрузка...' : '🔄 Обновить из API'}
        </button>
      </div>

      {/* Поля для API ключей */}
      {showApiKeyInput && (
        <div className="api-keys-section">
          <div className="api-key-input">
            <label>API ключ {PLATFORMS.find(p => p.id === sourcePlatform)?.name}:</label>
            <input
              type="text"
              value={sourceApiKey}
              onChange={(e) => setSourceApiKey(e.target.value)}
              placeholder="client_id:api_key"
              className="form-input"
            />
          </div>
          <div className="api-key-input">
            <label>API ключ {PLATFORMS.find(p => p.id === targetPlatform)?.name}:</label>
            <input
              type="text"
              value={targetApiKey}
              onChange={(e) => setTargetApiKey(e.target.value)}
              placeholder="client_id:api_key или token"
              className="form-input"
            />
          </div>
          <div className="mapping-hint">
            💡 Оставьте пустым для использования встроенных справочников
          </div>
        </div>
      )}

      {/* Колонки с категориями */}
      <div className="mapping-columns">
        <div className="mapping-column">
          <h3>{PLATFORMS.find(p => p.id === sourcePlatform)?.name} ({sourceCategories.length})</h3>
          <div className="category-list">
            {sourceCategories.map(cat => (
              <div
                key={cat.id}
                className={`category-item ${selectedSource?.id === cat.id ? 'selected' : ''}`}
                onClick={() => setSelectedSource(cat)}
                style={{ paddingLeft: `${cat.level * 20}px` }}
              >
                {cat.name}
              </div>
            ))}
          </div>
        </div>

        <div className="mapping-column">
          <h3>{PLATFORMS.find(p => p.id === targetPlatform)?.name} ({targetCategories.length})</h3>
          <div className="category-list">
            {targetCategories.map(cat => (
              <div
                key={cat.id}
                className={`category-item ${selectedTarget?.id === cat.id ? 'selected' : ''}`}
                onClick={() => setSelectedTarget(cat)}
                style={{ paddingLeft: `${cat.level * 20}px` }}
              >
                {cat.name}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Кнопка сохранения */}
      {selectedSource && selectedTarget && (
        <div className="mapping-save-section">
          <div className="mapping-preview">
            <span className="mapping-from">{selectedSource.name}</span>
            <span className="mapping-arrow">→</span>
            <span className="mapping-to">{selectedTarget.name}</span>
          </div>
          <button className="btn btn-primary" onClick={handleSaveMapping}>
            💾 Сохранить маппинг
          </button>
        </div>
      )}

      {/* Сохраненные маппинги */}
      {mappings.length > 0 && (
        <div className="saved-mappings">
          <h3>Сохраненные маппинги:</h3>
          <div className="mappings-list">
            {mappings.map((m, i) => (
              <div key={i} className="mapping-item">
                {m.source.name} → {m.target.name}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default CategoryMapping;