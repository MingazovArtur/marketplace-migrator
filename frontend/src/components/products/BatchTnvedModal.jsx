import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api } from '../../api';

/**
 * ✅ Массовый подбор ТН ВЭД для выбранных товаров.
 *
 * Два режима:
 *  1. «Авто» — сервер подбирает кандидатов по названию/категории каждого товара;
 *     показываем агрегат (какие коды подходят чаще всего) + вручную поиск.
 *  2. Применение выбранного кода ко ВСЕМ выбранным товарам одним кликом.
 *
 * Операция откатываемая: бэкенд пишет undo-снапшот прежних okpd_code
 * (кнопка «Отменить» после применения / «Отменить последнее изменение»).
 */
const BatchTnvedModal = ({ isOpen, onClose, selectedIds = [], onSaved }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null); // ответ batch-suggest
  const [selectedCode, setSelectedCode] = useState(null);
  const [searchText, setSearchText] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    setData(null);
    setError('');
    setSelectedCode(null);
    setSearchText('');
    setSearchResults([]);
    setApplying(false);
    setResult(null);
    setLoading(true);
    api
      .tnvedBatchSuggest(selectedIds)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [isOpen, selectedIds]);

  // Живой поиск по справочнику (debounce 500 мс)
  useEffect(() => {
    if (!isOpen) return undefined;
    const text = searchText.trim();
    if (text.length < 2) {
      setSearchResults([]);
      return undefined;
    }
    const t = setTimeout(async () => {
      try {
        const res = await fetch(`/api/tnved/search?query=${encodeURIComponent(text)}`);
        const d = await res.json();
        setSearchResults((d.results || []).slice(0, 8));
      } catch {
        setSearchResults([]);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [searchText, isOpen]);

  const handleApply = useCallback(
    async (code) => {
      if (!code || applying) return;
      setApplying(true);
      setError('');
      try {
        const res = await api.tnvedBatchApply(selectedIds, code);
        setResult(res);
        onSaved?.();
      } catch (e) {
        setError(e.message);
      } finally {
        setApplying(false);
      }
    },
    [selectedIds, applying, onSaved]
  );

  const perProductSuggestions = useMemo(
    () => (data?.results || []).filter((r) => (r.suggestions || []).length > 0 || r.okpd_code),
    [data]
  );

  if (!isOpen) return null;

  const candidates = searchResults.length
    ? searchResults.map((r) => ({ code: r.code, description: r.description, count: null }))
    : (data?.aggregated || []).map((a) => ({ ...a, count: a.count }));

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="search" size={22} /> Массовый подбор ТН ВЭД ({selectedIds.length})
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        {result ? (
          /* ✅ Финал: код применён */
          <div style={{ padding: '0.5rem 0' }}>
            <div className="alert alert-success">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Icon name="check" size={16} /> Код {result.code} прописан {result.updated} товарам.
                {result.description ? ` (${result.description})` : ''}
              </div>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Можно отменить: «Отменить последнее изменение» на странице «Товары».
            </p>
            <div className="modal-actions">
              <Button onClick={onClose}>Готово</Button>
            </div>
          </div>
        ) : (
          <>
            {loading && (
              <div
                className="progress-status"
                style={{
                  display: 'flex',
                  gap: '0.5rem',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <div className="spinner spinner-dark" /> Подбираем коды по названиям товаров...
              </div>
            )}

            {error && (
              <div className="alert alert-error">
                <div>{error}</div>
              </div>
            )}

            {data && (
              <>
                {/* Итог авто-подбора */}
                <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
                  <h4
                    style={{
                      margin: '0 0 0.5rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                    }}
                  >
                    <Icon name="check" size={16} /> Авто-подбор по {data.total} товарам
                  </h4>
                  <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                    Подобрано для <strong>{data.with_suggestions}</strong> из {data.total}
                    {data.already_set > 0 && (
                      <> · у {data.already_set} код уже стоит (будет перезаписан)</>
                    )}
                  </p>
                </div>

                {/* Кандидаты */}
                {candidates.length > 0 && (
                  <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
                    <h4 style={{ margin: '0 0 0.5rem' }}>
                      {searchResults.length
                        ? 'Результаты поиска'
                        : 'Кандидаты (подходят большинству товаров)'}
                    </h4>
                    {candidates.map((c) => (
                      <label
                        key={c.code}
                        className="bulk-check"
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.6rem',
                          padding: '0.45rem 0.6rem',
                          marginBottom: '0.3rem',
                          background:
                            selectedCode === c.code
                              ? 'rgba(99,102,241,0.15)'
                              : 'var(--bg-secondary)',
                          border: `1px solid ${selectedCode === c.code ? 'var(--primary, #3b82f6)' : 'transparent'}`,
                          borderRadius: '8px',
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="radio"
                          name="tnved-code"
                          checked={selectedCode === c.code}
                          onChange={() => setSelectedCode(c.code)}
                        />
                        <span style={{ fontWeight: 600, minWidth: '5.5rem' }}>{c.code}</span>
                        <span style={{ color: 'var(--text-secondary)', flex: 1 }}>
                          {c.description}
                        </span>
                        {c.count != null && (
                          <span
                            title="Скольким товарам подходит этот код"
                            style={{
                              padding: '0.1rem 0.5rem',
                              borderRadius: 999,
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              background: 'rgba(34,197,94,0.15)',
                              color: 'var(--success, #22c55e)',
                            }}
                          >
                            {c.count} тов.
                          </span>
                        )}
                      </label>
                    ))}
                  </div>
                )}

                {/* Поиск по справочнику */}
                <div className="form-group">
                  <label className="form-label">
                    Или найдите код в справочнике (слово, часть кода, описание):
                  </label>
                  <input
                    className="form-input"
                    type="text"
                    value={searchText}
                    placeholder="например: футболка или 6109"
                    onChange={(e) => setSearchText(e.target.value)}
                  />
                </div>

                {/* Что подобрано поштучно */}
                {perProductSuggestions.length > 0 && (
                  <details style={{ marginBottom: '0.75rem' }}>
                    <summary
                      style={{
                        cursor: 'pointer',
                        color: 'var(--text-secondary)',
                        fontSize: '0.85rem',
                      }}
                    >
                      Поштучно: у каких товаров что подобрано ({perProductSuggestions.length})
                    </summary>
                    <ul style={{ listStyle: 'none', padding: '0.4rem 0 0', margin: 0 }}>
                      {perProductSuggestions.slice(0, 30).map((r) => (
                        <li
                          key={r.product_id}
                          style={{
                            padding: '0.4rem 0.6rem',
                            marginBottom: '0.3rem',
                            background: 'var(--bg-secondary)',
                            borderRadius: '6px',
                            fontSize: '0.85rem',
                          }}
                        >
                          <strong>#{r.product_id}</strong> {r.name}
                          {r.okpd_code && (
                            <span style={{ color: 'var(--warning, #f59e0b)' }}>
                              {' '}
                              (сейчас: {r.okpd_code})
                            </span>
                          )}
                          <div style={{ color: 'var(--text-secondary)' }}>
                            {(r.suggestions || [])
                              .map((s) => `${s.code} (${s.description})`)
                              .join('; ') || 'нет подсказок — подберите вручную выше'}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}

                <div className="modal-actions">
                  <Button variant="outline" onClick={onClose} disabled={applying}>
                    Отмена
                  </Button>
                  <Button
                    onClick={() => handleApply(selectedCode)}
                    disabled={!selectedCode || applying || loading}
                    loading={applying}
                  >
                    <Icon name="check" size={16} /> Прописать {selectedCode || ''} всем выбранным
                  </Button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default BatchTnvedModal;
