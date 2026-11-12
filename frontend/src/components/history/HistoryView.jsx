import React, { useState, useEffect, useCallback } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api } from '../../api';
import EmptyState from '../common/EmptyState';

const TYPE_META = {
  import: { label: 'Импорт', icon: 'import' },
  export: { label: 'Экспорт', icon: 'export' },
  migration: { label: 'Миграция', icon: 'migrate' },
  media: { label: 'Медиа', icon: 'photo' },
};

// ✅ v4: типы операций правки товаров (аудит-лог + undo)
const EDIT_ACTION_META = {
  bulk_update: { label: 'Массовое обновление', icon: 'edit' },
  edit: { label: 'Правка товара', icon: 'edit' },
  logistics: { label: 'Логистика', icon: 'edit' },
  tnved: { label: 'ТН ВЭД', icon: 'search' },
  defaults: { label: 'Дозаполнение дефолтами', icon: 'edit' },
};

const EDIT_FIELD_LABELS = {
  name: 'Название',
  price: 'Цена',
  brand: 'Бренд',
  mapped_category: 'Категория',
  vat_rate: 'НДС',
  okpd_code: 'ТН ВЭД',
  barcode: 'Штрихкод',
  weight_grams: 'Вес',
  package_weight_grams: 'Вес упаковки',
  package_width_mm: 'Ширина',
  package_height_mm: 'Высота',
  package_length_mm: 'Длина',
  stock: 'Остаток',
  units_per_item: 'Ед. в товаре',
};

const STATUS_META = {
  success: { label: 'Успешно', cls: 'badge-success' },
  partial: { label: 'Частично', cls: 'badge-pending' },
  error: { label: 'Ошибка', cls: 'badge-error' },
};

const FILTERS = [
  { id: '', label: 'Все' },
  { id: 'import', label: 'Импорт', icon: 'import' },
  { id: 'migration', label: 'Миграции', icon: 'migrate' },
  { id: 'export', label: 'Экспорт', icon: 'export' },
];

const formatDate = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const HistoryView = () => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  // ✅ v4: аудит-лог правок товаров + undo
  const [editHistory, setEditHistory] = useState([]);
  const [undoBusyId, setUndoBusyId] = useState(null);
  const [editMsg, setEditMsg] = useState('');

  const loadEditHistory = useCallback(async () => {
    try {
      const d = await api.getEditHistory(20);
      setEditHistory(d.history || []);
    } catch {
      setEditHistory([]);
    }
  }, []);

  const handleUndo = useCallback(
    async (snapshotId) => {
      if (undoBusyId) return;
      setUndoBusyId(snapshotId);
      setEditMsg('');
      try {
        const r = await api.bulkUndoProducts(snapshotId);
        setEditMsg(
          `↩ Отменено: восстановлено ${r.restored} из ${r.restored + (r.skipped_missing || 0)}` +
            (r.label ? ` — ${r.label}` : '')
        );
        await loadEditHistory();
      } catch (e) {
        setEditMsg('❌ ' + e.message);
      } finally {
        setUndoBusyId(null);
      }
    },
    [undoBusyId, loadEditHistory]
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getHistory({ operation: filter || undefined, limit: 100 });
      setHistory(data.history || []);
    } catch (e) {
      console.error('Ошибка загрузки истории:', e);
      setHistory([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadEditHistory();
  }, [loadEditHistory]);

  const renderEmptyState = () => {
    // Сценарий 1: фильтр активен, но по нему ничего не найдено
    if (filter) {
      return (
        <EmptyState
          icon={<Icon name="search" size={56} />}
          title="По выбранному фильтру ничего не найдено"
          description="Попробуйте выбрать другой тип операции или сбросить фильтр."
          actionLabel="Показать все операции"
          onAction={() => setFilter('')}
        />
      );
    }
    // Сценарий 2: история полностью пуста
    return (
      <EmptyState
        icon={<Icon name="history" size={56} />}
        title="История операций пуста"
        description="Здесь будут отображаться все ваши импорты, миграции и выгрузки. Импортируйте первый файл — и журнал заполнится."
        actionLabel="Перейти к импорту"
        onAction={() => {
          window.location.hash = '#/';
        }}
        secondaryLabel="Как это работает"
        onSecondary={() => {
          window.location.hash = '#/help';
        }}
      />
    );
  };

  return (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">История операций</h1>
          <p className="header-subtitle">Журнал импортов, миграций и экспортов</p>
        </div>
        <div className="header-actions">
          <Button variant="secondary" onClick={load} disabled={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
        </div>
      </header>

      {/* Фильтры по типу операции */}
      <div className="products-toolbar">
        {FILTERS.map((f) => (
          <Button
            key={f.id || 'all'}
            variant={filter === f.id ? 'primary' : 'secondary'}
            onClick={() => setFilter(f.id)}
          >
            {f.icon && <Icon name={f.icon} size={16} />} {f.label}
          </Button>
        ))}
      </div>

      {/* ✅ v4: аудит-лог правок товаров (undo доступен для неотменённых) */}
      {editHistory.length > 0 && (
        <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.9rem' }}>
          <h4
            style={{ margin: '0 0 0.6rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
          >
            <Icon name="edit" size={16} /> История изменений товаров
          </h4>
          {editMsg && (
            <div
              className="alert alert-success"
              style={{ marginBottom: '0.6rem', fontSize: '0.85rem' }}
            >
              <div>{editMsg}</div>
            </div>
          )}
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {editHistory.slice(0, 10).map((e) => {
              const meta = EDIT_ACTION_META[e.action] || { label: e.action, icon: 'edit' };
              return (
                <li
                  key={e.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    padding: '0.45rem 0.6rem',
                    marginBottom: '0.3rem',
                    background: 'var(--bg-secondary)',
                    borderRadius: '8px',
                    opacity: e.undone ? 0.55 : 1,
                    flexWrap: 'wrap',
                  }}
                >
                  <span className="type-badge" style={{ fontSize: '0.8rem' }}>
                    <Icon name={meta.icon} size={14} /> {meta.label}
                  </span>
                  <span style={{ flex: 1, minWidth: 200, fontSize: '0.85rem' }}>
                    {e.label || (
                      <>
                        {(e.fields || []).map((f) => EDIT_FIELD_LABELS[f] || f).join(', ')} ·{' '}
                        {e.items_count} тов.
                      </>
                    )}
                  </span>
                  <span
                    style={{
                      color: 'var(--text-secondary)',
                      fontSize: '0.8rem',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {formatDate(e.created_at)}
                  </span>
                  {e.undone ? (
                    <span
                      className="badge badge-pending"
                      title="Значения восстановлены к состоянию до операции"
                    >
                      Отменено
                    </span>
                  ) : (
                    <Button
                      variant="outline"
                      size="small"
                      onClick={() => handleUndo(e.id)}
                      disabled={!!undoBusyId}
                      title="Вернуть прежние значения полей"
                    >
                      ↩ Отменить
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Таблица истории */}
      <div className="table-container">
        {loading ? (
          <div className="progress-status">Загрузка истории...</div>
        ) : history.length === 0 ? (
          renderEmptyState()
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 160 }}>Дата</th>
                  <th style={{ width: 150 }}>Тип</th>
                  <th>Описание</th>
                  <th style={{ width: 240 }}>Показатели</th>
                  <th style={{ width: 120 }}>Статус</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => {
                  const t = TYPE_META[h.type] || TYPE_META.import;
                  const s = STATUS_META[h.status] || STATUS_META.error;
                  return (
                    <tr key={h.id}>
                      <td style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        {formatDate(h.created_at)}
                      </td>
                      <td>
                        <span className="type-badge">
                          <Icon name={t.icon} size={18} /> {t.label}
                        </span>
                      </td>
                      <td>
                        <div className="product-name" title={h.description}>
                          {h.description}
                        </div>
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
