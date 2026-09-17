import React, { useState, useEffect, useCallback } from 'react';
import Button from '../common/Button';
import { api } from '../../api';

const TYPE_META = {
  import:    { label: 'Импорт',   icon: '📥', cls: 'badge-pending' },
  export:    { label: 'Экспорт',  icon: '📤', cls: 'badge-processing' },
  migration: { label: 'Миграция', icon: '🔄', cls: 'badge-success' },
  media: { label: 'Медиа', icon: '💾', cls: 'badge-processing' },
};

const STATUS_META = {
  success: { label: 'Успешно',  cls: 'badge-success' },
  partial: { label: 'Частично', cls: 'badge-pending' },
  error:   { label: 'Ошибка',   cls: 'badge-error' },
};

const HistoryView = () => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getHistory(filter ? { operation: filter, limit: 100 } : { limit: 100 });
      setHistory(data.history || []);
    } catch (e) {
      console.error('Ошибка загрузки истории:', e);
      setHistory([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">История операций</h1>
          <p className="header-subtitle">Журнал импортов, миграций и экспортов</p>
        </div>
        <div className="header-actions">
          <Button variant="secondary" onClick={load} disabled={loading}>🔄 Обновить</Button>
        </div>
      </header>

      <div className="products-toolbar">
        {[
          { id: '', label: 'Все' },
          { id: 'import', label: '📥 Импорт' },
          { id: 'migration', label: '🔄 Миграции' },
          { id: 'export', label: '📤 Экспорт' },
        ].map(f => (
          <Button
            key={f.id}
            variant={filter === f.id ? 'primary' : 'secondary'}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </Button>
        ))}
      </div>

      <div className="table-container">
        {loading ? (
          <div className="progress-status">⏳ Загрузка истории...</div>
        ) : history.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📜</div>
            <p className="empty-state-text">История пуста. Выполните импорт или миграцию.</p>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th style={{ width: '170px' }}>Дата</th>
                  <th style={{ width: '110px' }}>Тип</th>
                  <th>Описание</th>
                  <th style={{ width: '220px' }}>Показатели</th>
                  <th style={{ width: '120px' }}>Статус</th>
                </tr>
              </thead>
              <tbody>
                {history.map(h => {
                  const t = TYPE_META[h.type] || TYPE_META.import;
                  const s = STATUS_META[h.status] || STATUS_META.error;
                  return (
                    <tr key={h.id}>
                      <td style={{ color: 'var(--text-secondary)' }}>
                        {h.created_at ? new Date(h.created_at).toLocaleString('ru-RU') : '—'}
                      </td>
                      <td>
                        <span className={`badge ${t.cls}`}>{t.icon} {t.label}</span>
                      </td>
                      <td>
                        <div className="product-name" title={h.description}>{h.description}</div>
                        {h.error_message && (
                          <div className="product-sub" style={{ color: 'var(--accent-danger)' }}>
                            {h.error_message}
                          </div>
                        )}
                      </td>
                      <td style={{ color: 'var(--text-secondary)' }}>{h.counts}</td>
                      <td>
                        <span className={`badge ${s.cls}`}>{s.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
};

export default HistoryView;