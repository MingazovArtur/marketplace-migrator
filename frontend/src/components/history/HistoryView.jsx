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
