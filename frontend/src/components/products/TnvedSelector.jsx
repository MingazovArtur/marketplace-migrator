import React, { useState, useEffect, useCallback } from 'react';
import Icon from '../icons';

/**
 * Компонент выбора кода ТН ВЭД с автоподсказками.
 */
const TnvedSelector = ({ value, onChange, productName = '', category = '', disabled = false }) => {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [searchText, setSearchText] = useState('');

  // Debounced запрос к API для получения подсказок
  const fetchSuggestions = useCallback(
    async (text) => {
      if (!text || text.length < 2) {
        setSuggestions([]);
        return;
      }

      setLoading(true);
      try {
        const response = await fetch(
          `/api/tnved/suggest?name=${encodeURIComponent(text)}&category=${encodeURIComponent(category)}`
        );
        const data = await response.json();
        if (data.success) {
          setSuggestions(data.suggestions || []);
        }
      } catch (error) {
        console.error('Ошибка получения подсказок ТН ВЭД:', error);
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    },
    [category]
  );

  // Эффект с задержкой (debounce) для предотвращения лишних запросов при вводе
  useEffect(() => {
    const timer = setTimeout(() => {
      // Используем searchText (то, что в поле) ИЛИ productName (из товара)
      const textToSearch = searchText || productName;
      if (textToSearch) {
        fetchSuggestions(textToSearch);
      } else {
        setSuggestions([]);
      }
    }, 600); // Задержка 600 мс

    return () => clearTimeout(timer);
  }, [searchText, productName, category, fetchSuggestions]);

  const handleSelect = (code) => {
    onChange(code);
    setSuggestions([]);
    setShowDropdown(false);
  };

  return (
    <div className="form-group" style={{ position: 'relative' }}>
      <label className="form-label">
        Код ТН ВЭД ЕАЭС
        <span
          style={{
            color: 'var(--text-muted)',
            fontWeight: 'normal',
            fontSize: '0.85rem',
            marginLeft: '0.5rem',
          }}
        >
          (введите название для автоподбора или код вручную)
        </span>
      </label>

      <div style={{ position: 'relative' }}>
        <input
          className="form-input"
          type="text"
          value={value || ''}
          onChange={(e) => {
            const val = e.target.value;
            onChange(val);
            setSearchText(val); // Сохраняем для поиска
            setShowDropdown(true);
          }}
          onFocus={() => {
            setShowDropdown(true);
            // Если поле пустое, используем productName для поиска
            if (!value && productName) {
              setSearchText(productName);
            }
          }}
          placeholder="Например: 6109100000 или введите 'футболка'"
          disabled={disabled}
          style={{ paddingRight: '2.5rem' }}
        />

        {value && (
          <button
            type="button"
            onClick={() => {
              onChange('');
              setSuggestions([]);
              setSearchText('');
            }}
            style={{
              position: 'absolute',
              right: '0.5rem',
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-muted)',
              padding: '0.25rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Очистить"
          >
            <Icon name="close" size={14} />
          </button>
        )}
      </div>

      {/* Индикатор загрузки */}
      {loading && (
        <div
          style={{
            fontSize: '0.85rem',
            color: 'var(--text-muted)',
            marginTop: '0.25rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
          }}
        >
          <div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
          Ищем код ТН ВЭД...
        </div>
      )}

      {/* Выпадающий список с подсказками */}
      {showDropdown && suggestions.length > 0 && !loading && (
        <div
          className="tnved-suggestions-dropdown"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: '0.25rem',
            padding: '0.5rem',
            background: 'var(--bg-primary, #ffffff)',
            borderRadius: '8px',
            border: '1px solid var(--border-color, #e5e7eb)',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
            zIndex: 50,
            maxHeight: '300px',
            overflowY: 'auto',
          }}
        >
          <div
            style={{
              fontSize: '0.8rem',
              fontWeight: 600,
              color: 'var(--text-muted)',
              marginBottom: '0.5rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            💡 Рекомендуемые коды:
          </div>
          {suggestions.map((s, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSelect(s.code)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '0.6rem 0.75rem',
                marginBottom: idx < suggestions.length - 1 ? '0.25rem' : 0,
                background: 'transparent',
                border: '1px solid var(--border-color, #e5e7eb)',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.9rem',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--hover-bg, #f3f4f6)';
                e.currentTarget.style.borderColor = 'var(--primary, #3b82f6)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.borderColor = 'var(--border-color, #e5e7eb)';
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  color: 'var(--text-primary, #111827)',
                  marginBottom: '0.15rem',
                }}
              >
                {s.code}
              </div>
              <div
                style={{
                  fontSize: '0.85rem',
                  color: 'var(--text-secondary, #4b5563)',
                  lineHeight: 1.3,
                }}
              >
                {s.description}
              </div>
              <div
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-muted, #9ca3af)',
                  marginTop: '0.25rem',
                }}
              >
                Найдено по слову: «{s.keyword}»
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Клик вне dropdown закрывает его */}
      {showDropdown && (
        <div
          style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 40 }}
          onClick={() => setShowDropdown(false)}
        />
      )}
    </div>
  );
};

export default TnvedSelector;
