import React, { useState } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { formatDate } from './specsUtils';

/* =====================================================================
   Модалка просмотра атрибутов (с lazy-loading)
   Р3: вынесено из SpecsPage.jsx без изменения логики.
   ===================================================================== */
const SpecDetailModal = ({ spec, loading, error, onClose }) => {
  const [search, setSearch] = useState('');
  const [onlyRequired, setOnlyRequired] = useState(false);

  const attrs = spec?.spec?.attributes || [];
  const q = search.trim().toLowerCase();

  const filtered = attrs.filter((a) => {
    if (onlyRequired && !a.required) return false;
    if (q && !a.name.toLowerCase().includes(q) && !String(a.id).toLowerCase().includes(q))
      return false;
    return true;
  });

  const requiredCount = attrs.filter((a) => a.required).length;

  const typeLabel = (t) =>
    ({
      number: 'Число',
      text: 'Текст',
      select: 'Выбор',
      multiselect: 'Множ. выбор',
    })[t] || t;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="layers" size={22} /> {spec?.category_name || 'Загрузка...'}
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        {/* Состояние загрузки */}
        {loading && (
          <div style={{ padding: '2rem', textAlign: 'center' }}>
            <div className="spinner" style={{ margin: '0 auto 1rem' }} />
            <p style={{ color: 'var(--text-secondary)' }}>Загружаем атрибуты категории...</p>
          </div>
        )}

        {/* Ошибка загрузки */}
        {error && !loading && (
          <div className="alert alert-error">
            <div>❌ Не удалось загрузить атрибуты: {error}</div>
          </div>
        )}

        {/* Успешная загрузка — полный контент */}
        {spec && !loading && (
          <>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1rem' }}>
              ID: {spec.category_id} · Обновлён: {formatDate(spec.fetched_at)} · Версия:{' '}
              {spec.version || '—'}
            </div>

            <div className="export-validation" style={{ marginBottom: '1rem' }}>
              <div className="validation-card">
                <div className="validation-num">{attrs.length}</div>
                <div>атрибутов</div>
              </div>
              <div className="validation-card ready">
                <div className="validation-num">{requiredCount}</div>
                <div>обязательных</div>
              </div>
              <div className="validation-card warn">
                <div className="validation-num">
                  {attrs.filter((a) => a.values && a.values.length > 0).length}
                </div>
                <div>со словарями</div>
              </div>
              <div className="validation-card">
                <div className="validation-num">{spec.spec?.sheets?.length || 0}</div>
                <div>листов XLS</div>
              </div>
            </div>

            <div
              style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}
            >
              <input
                className="form-input"
                placeholder="Поиск по названию или ID..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ flex: 1, minWidth: 200 }}
              />
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  fontSize: '0.85rem',
                  color: 'var(--text-secondary)',
                  whiteSpace: 'nowrap',
                }}
              >
                <input
                  type="checkbox"
                  checked={onlyRequired}
                  onChange={(e) => setOnlyRequired(e.target.checked)}
                />
                Только обязательные
              </label>
            </div>

            <div
              style={{
                maxHeight: '50vh',
                overflowY: 'auto',
                border: '1px solid var(--border-color)',
                borderRadius: 8,
              }}
            >
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead
                  style={{
                    position: 'sticky',
                    top: 0,
                    background: 'var(--bg-secondary)',
                    zIndex: 1,
                  }}
                >
                  <tr>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '0.6rem',
                        borderBottom: '1px solid var(--border-color)',
                      }}
                    >
                      ID
                    </th>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '0.6rem',
                        borderBottom: '1px solid var(--border-color)',
                      }}
                    >
                      Название
                    </th>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '0.6rem',
                        borderBottom: '1px solid var(--border-color)',
                      }}
                    >
                      Тип
                    </th>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '0.6rem',
                        borderBottom: '1px solid var(--border-color)',
                      }}
                    >
                      Группа
                    </th>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '0.6rem',
                        borderBottom: '1px solid var(--border-color)',
                      }}
                    >
                      Значения
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((a) => (
                    <tr key={a.id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                      <td
                        style={{
                          padding: '0.6rem',
                          color: 'var(--text-muted)',
                          fontFamily: 'monospace',
                          fontSize: '0.8rem',
                        }}
                      >
                        {a.id}
                      </td>
                      <td style={{ padding: '0.6rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          {a.required && (
                            <span
                              style={{ color: 'var(--accent-danger)', fontWeight: 700 }}
                              title="Обязательное"
                            >
                              *
                            </span>
                          )}
                          {a.name}
                        </div>
                      </td>
                      <td style={{ padding: '0.6rem' }}>
                        <span className="badge badge-pending">{typeLabel(a.type)}</span>
                      </td>
                      <td style={{ padding: '0.6rem', color: 'var(--text-secondary)' }}>
                        {a.group}
                      </td>
                      <td style={{ padding: '0.6rem' }}>
                        {a.values && a.values.length > 0 ? (
                          <div
                            style={{
                              display: 'flex',
                              flexWrap: 'wrap',
                              gap: '0.25rem',
                              maxWidth: 300,
                            }}
                          >
                            {a.values.slice(0, 3).map((v, i) => (
                              <span key={i} className="attr-chip" style={{ fontSize: '0.75rem' }}>
                                {v}
                              </span>
                            ))}
                            {a.values.length > 3 && (
                              <span className="attr-chip more" style={{ fontSize: '0.75rem' }}>
                                +{a.values.length - 3}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}
                      >
                        Ничего не найдено
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {loading ? 'Загрузка...' : 'Закрыть'}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default SpecDetailModal;
