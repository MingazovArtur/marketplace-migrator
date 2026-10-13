import React, { useState, useEffect, useMemo, useCallback } from 'react';
import './App.css';
import Icon from './components/icons';

const API_URL = 'http://localhost:8000/api';
const PLATFORMS = [
  { id: 'ozon', name: 'Ozon', color: '#005bff' },
  { id: 'wildberries', name: 'Wildberries', color: '#cb11ab' },
  { id: 'yandex', name: 'Яндекс Маркет', color: '#fc3f1d' },
];

const authHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
  };
};

function CategoryMapping() {
  const [sourcePlatform, setSourcePlatform] = useState('ozon');
  const [targetPlatform, setTargetPlatform] = useState('wildberries');
  const [sourceCategories, setSourceCategories] = useState([]);
  const [targetCategories, setTargetCategories] = useState([]);
  const [selectedSource, setSelectedSource] = useState(null);
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [alertType, setAlertType] = useState('');
  const [sourceSearch, setSourceSearch] = useState('');
  const [targetSearch, setTargetSearch] = useState('');
  const [onlyUnmapped, setOnlyUnmapped] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const [sourceApiKey, setSourceApiKey] = useState('');
  const [targetApiKey, setTargetApiKey] = useState('');
  const [showApiKeyInput, setShowApiKeyInput] = useState(false);

  const showAlert = useCallback((text, type = 'success') => {
    setMessage(text);
    setAlertType(type);
  }, []);

  const clearAlert = useCallback(() => {
    setMessage('');
    setAlertType('');
  }, []);

  /* ==================== 1. СНАЧАЛА объявляем функции ==================== */
  const loadCategories = useCallback(async (useApiKey = false) => {
    setLoading(true);
    clearAlert();

    try {
      if (useApiKey && sourceApiKey) {
        const res = await fetch(`${API_URL}/categories/${sourcePlatform}/refresh`, {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify({ api_key: sourceApiKey }),
        });
        const data = await res.json();
        setSourceCategories(data.categories || []);
      } else {
        const res = await fetch(`${API_URL}/categories/${sourcePlatform}`);
        const data = await res.json();
        setSourceCategories(data.categories || []);
      }

      if (useApiKey && targetApiKey) {
        const res = await fetch(`${API_URL}/categories/${targetPlatform}/refresh`, {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify({ api_key: targetApiKey }),
        });
        const data = await res.json();
        setTargetCategories(data.categories || []);
      } else {
        const res = await fetch(`${API_URL}/categories/${targetPlatform}`);
        const data = await res.json();
        setTargetCategories(data.categories || []);
      }

      if (useApiKey) showAlert('Справочники обновлены из API', 'success');
    } catch (error) {
      showAlert('Ошибка загрузки категорий', 'error');
    } finally {
      setLoading(false);
    }
  }, [sourcePlatform, targetPlatform, sourceApiKey, targetApiKey, clearAlert, showAlert]);

  const loadMappings = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_URL}/category-mapping?source_platform=${sourcePlatform}&target_platform=${targetPlatform}`,
        { headers: authHeaders() }
      );
      if (res.ok) {
        const data = await res.json();
        setMappings(data.mappings || []);
      }
    } catch (e) {
      console.error('Ошибка загрузки маппингов:', e);
    }
  }, [sourcePlatform, targetPlatform]);

  /* ==================== 2. ТЕПЕРЬ useEffect (безопасно) ==================== */
  useEffect(() => {
    loadCategories();
    loadMappings();
    setSelectedSource(null);
    setSelectedTarget(null);
  }, [sourcePlatform, targetPlatform, loadCategories, loadMappings]);

  /* ==================== 3. Остальная логика ==================== */
  const handleSaveMapping = async () => {
    if (!selectedSource || !selectedTarget) {
      showAlert('Выберите категории с обеих сторон', 'warning');
      return;
    }

    try {
      const res = await fetch(
        `${API_URL}/category-mapping?source_platform=${sourcePlatform}&source_category_id=${selectedSource.id}&target_platform=${targetPlatform}&target_category_id=${selectedTarget.id}`,
        { method: 'POST', headers: authHeaders() }
      );
      const data = await res.json();

      if (data.success) {
        showAlert(`Маппинг сохранён: ${selectedSource.name} → ${selectedTarget.name}`, 'success');
        setSelectedSource(null);
        setSelectedTarget(null);
        await loadMappings();
      } else {
        showAlert('Ошибка сохранения маппинга', 'error');
      }
    } catch (error) {
      showAlert('Ошибка соединения с сервером', 'error');
    }
  };

  const handleDeleteMapping = async (mapping) => {
    try {
      const res = await fetch(`${API_URL}/category-mapping/${mapping.id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (res.ok) {
        showAlert('Маппинг удалён', 'success');
        setConfirmDeleteId(null);
        await loadMappings();
      } else {
        showAlert('Ошибка удаления маппинга', 'error');
      }
    } catch (e) {
      showAlert('Ошибка соединения с сервером', 'error');
    }
  };

  const filteredSource = useMemo(() => {
    const q = sourceSearch.trim().toLowerCase();
    if (!q) return sourceCategories;
    return sourceCategories.filter((c) => c.name.toLowerCase().includes(q));
  }, [sourceCategories, sourceSearch]);

  const filteredTarget = useMemo(() => {
    const q = targetSearch.trim().toLowerCase();
    if (!q) return targetCategories;
    return targetCategories.filter((c) => c.name.toLowerCase().includes(q));
  }, [targetCategories, targetSearch]);

  const coverage = useMemo(() => {
    const mappedSourceIds = new Set(mappings.map((m) => String(m.source_category_id)));
    const mappedTargetIds = new Set(mappings.map((m) => String(m.target_category_id)));
    const total = sourceCategories.length;
    const covered = sourceCategories.filter((c) => mappedSourceIds.has(String(c.id))).length;
    const percent = total > 0 ? Math.round((covered / total) * 100) : 0;
    return {
      covered,
      total,
      percent,
      remaining: total - covered,
      mappedSourceIds,
      mappedTargetIds,
    };
  }, [mappings, sourceCategories]);

  const visibleSource = useMemo(() => {
    if (!onlyUnmapped) return filteredSource;
    return filteredSource.filter((c) => !coverage.mappedSourceIds.has(String(c.id)));
  }, [filteredSource, onlyUnmapped, coverage.mappedSourceIds]);

  const sourceNameById = useMemo(
    () => new Map(sourceCategories.map((c) => [String(c.id), c.name])),
    [sourceCategories]
  );
  const targetNameById = useMemo(
    () => new Map(targetCategories.map((c) => [String(c.id), c.name])),
    [targetCategories]
  );

  const sourceName = PLATFORMS.find((p) => p.id === sourcePlatform)?.name;
  const targetName = PLATFORMS.find((p) => p.id === targetPlatform)?.name;

  return (
    <div className="category-mapping-container">
      <div className="mapping-header">
        <h2>
          <Icon name="mapping" size={26} />
          Настройка маппинга категорий
        </h2>
      </div>

      {message && alertType && (
        <div className={`alert alert-${alertType}`}>
          <div>{message}</div>
          <button onClick={clearAlert} className="alert-close" title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>
      )}

      <div className="mapping-platforms">
        <div className="platform-selector-group">
          <label>Источник:</label>
          <select
            value={sourcePlatform}
            onChange={(e) => setSourcePlatform(e.target.value)}
            className="form-input"
          >
            {PLATFORMS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="mapping-arrow">→</div>
        <div className="platform-selector-group">
          <label>Назначение:</label>
          <select
            value={targetPlatform}
            onChange={(e) => setTargetPlatform(e.target.value)}
            className="form-input"
          >
            {PLATFORMS.filter((p) => p.id !== sourcePlatform).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mapping-actions">
        <button className="btn btn-secondary" onClick={() => setShowApiKeyInput(!showApiKeyInput)}>
          <Icon name="key" size={16} /> {showApiKeyInput ? 'Скрыть' : 'Ввести'} API ключи
        </button>
        <button className="btn btn-primary" onClick={() => loadCategories(true)} disabled={loading}>
          <Icon name="refresh" size={16} /> {loading ? 'Загрузка...' : 'Обновить из API'}
        </button>
      </div>

      {showApiKeyInput && (
        <div className="api-keys-section">
          <div className="api-key-input">
            <label>API ключ {sourceName}:</label>
            <input
              type="text"
              value={sourceApiKey}
              onChange={(e) => setSourceApiKey(e.target.value)}
              placeholder="client_id:api_key"
              className="form-input"
            />
          </div>
          <div className="api-key-input">
            <label>API ключ {targetName}:</label>
            <input
              type="text"
              value={targetApiKey}
              onChange={(e) => setTargetApiKey(e.target.value)}
              placeholder="client_id:api_key или token"
              className="form-input"
            />
          </div>
          <div className="mapping-hint">
            <Icon name="help" size={16} />
            <span>Оставьте пустым для использования встроенных справочников</span>
          </div>
        </div>
      )}

      {sourceCategories.length > 0 && (
        <div className="mapping-coverage">
          <div className="mapping-coverage-head">
            <span>
              Покрытие маппинга ({sourceName} → {targetName})
            </span>
            <span>
              {coverage.covered} из {coverage.total} ({coverage.percent}%)
            </span>
          </div>
          <div className="mapping-coverage-bar">
            <div
              className={`mapping-coverage-fill ${coverage.percent === 100 ? 'full' : 'partial'}`}
              style={{ width: `${coverage.percent}%` }}
            />
          </div>
          <p className="mapping-coverage-hint">
            {coverage.percent === 100
              ? 'Все категории источника сопоставлены. Маппинг готов к миграции.'
              : `Осталось сопоставить: ${coverage.remaining}. Несопоставленные категории при миграции получат значение по умолчанию.`}
          </p>
        </div>
      )}

      <div className="mapping-columns">
        <div className="mapping-column">
          <h3>
            <span>
              {sourceName} ({visibleSource.length})
            </span>
            <label className="mapping-filter-toggle" title="Показать только несопоставленные категории">
              <input
                type="checkbox"
                checked={onlyUnmapped}
                onChange={(e) => setOnlyUnmapped(e.target.checked)}
              />
              Только несопоставленные ({coverage.remaining})
            </label>
          </h3>
          <div className="mapping-search">
            <input
              className="form-input"
              placeholder="Поиск категории..."
              value={sourceSearch}
              onChange={(e) => setSourceSearch(e.target.value)}
            />
          </div>
          <div className="category-list">
            {visibleSource.map((cat) => {
              const isMapped = coverage.mappedSourceIds.has(String(cat.id));
              return (
                <div
                  key={cat.id}
                  className={`category-item ${selectedSource?.id === cat.id ? 'selected' : ''}`}
                  onClick={() => setSelectedSource(cat)}
                  style={{ paddingLeft: `${8 + cat.level * 16}px` }}
                  title={`${cat.name} — ${isMapped ? 'сопоставлено' : 'НЕ сопоставлено'}`}
                >
                  <span className={`cat-dot ${isMapped ? 'mapped' : 'unmapped'}`} />
                  <span className="cat-name">{cat.name}</span>
                </div>
              );
            })}
            {visibleSource.length === 0 && (
              <div className="category-empty">
                {onlyUnmapped ? 'Все категории сопоставлены 🎉' : 'Ничего не найдено'}
              </div>
            )}
          </div>
        </div>

        <div className="mapping-column">
          <h3>
            <span>
              {targetName} ({filteredTarget.length})
            </span>
          </h3>
          <div className="mapping-search">
            <input
              className="form-input"
              placeholder="Поиск категории..."
              value={targetSearch}
              onChange={(e) => setTargetSearch(e.target.value)}
            />
          </div>
          <div className="category-list">
            {filteredTarget.map((cat) => {
              const isUsed = coverage.mappedTargetIds.has(String(cat.id));
              return (
                <div
                  key={cat.id}
                  className={`category-item ${selectedTarget?.id === cat.id ? 'selected' : ''}`}
                  onClick={() => setSelectedTarget(cat)}
                  style={{ paddingLeft: `${8 + cat.level * 16}px` }}
                  title={`${cat.name} — ${isUsed ? 'уже используется в маппинге' : 'свободна'}`}
                >
                  <span className={`cat-dot ${isUsed ? 'mapped' : 'free'}`} />
                  <span className="cat-name">{cat.name}</span>
                </div>
              );
            })}
            {filteredTarget.length === 0 && <div className="category-empty">Ничего не найдено</div>}
          </div>
        </div>
      </div>

      {selectedSource && selectedTarget && (
        <div className="mapping-save-section">
          <div className="mapping-preview">
            <span className="mapping-from">{selectedSource.name}</span>
            <span className="mapping-arrow-small">→</span>
            <span className="mapping-to">{selectedTarget.name}</span>
          </div>
          <button className="btn btn-primary" onClick={handleSaveMapping}>
            <Icon name="save" size={16} /> Сохранить маппинг
          </button>
        </div>
      )}

      {mappings.length > 0 && (
        <div className="saved-mappings">
          <h3>Сохранённые маппинги ({mappings.length}):</h3>
          <div className="mappings-list">
            {mappings.map((m) => (
              <div key={m.id} className="mapping-item">
                <span className="mapping-item-text">
                  {sourceNameById.get(String(m.source_category_id)) || `Категория ${m.source_category_id}`}
                  {' → '}
                  {targetNameById.get(String(m.target_category_id)) || `Категория ${m.target_category_id}`}
                </span>

                {confirmDeleteId === m.id ? (
                  <span className="mapping-item-confirm">
                    Удалить?
                    <button className="btn btn-danger btn-sm" onClick={() => handleDeleteMapping(m)}>
                      Да
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => setConfirmDeleteId(null)}>
                      Нет
                    </button>
                  </span>
                ) : (
                  <button
                    className="btn-icon-danger"
                    title="Удалить маппинг"
                    onClick={() => setConfirmDeleteId(m.id)}
                  >
                    <Icon name="close" size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default CategoryMapping;