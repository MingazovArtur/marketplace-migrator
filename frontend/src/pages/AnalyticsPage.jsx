import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import EmptyState from '../components/common/EmptyState';
import Icon from '../components/icons';
import { api } from '../api';

/* Аналитика селлера на собственных данных:
 * - заполненность полей (критические — без них экспорт невозможен)
 * - срез по категориям: цена/заполненность/маппинг
 * - история правок (bulk_edit_snapshots): активность и последние операции
 *
 * Тяжёлые полосы/графики — чистый CSS на переменных темы, без chart-библиотек. */

const fmtDate = (iso) => {
  if (!iso) return '—';
  const normalized = /[Z+]/.test(iso) ? iso : `${iso}Z`;
  return new Date(normalized).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const fmtDay = (iso) => {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
};

const EDIT_ACTION_LABELS = {
  bulk_update: 'массовое обновление',
  edit: 'правка товара',
  logistics: 'логистика',
  tnved: 'подбор ТН ВЭД',
  defaults: 'дозаполнение дефолтами',
};

const fill_color = (pct, critical) => {
  if (critical && pct < 70) return 'var(--accent-danger)';
  if (pct >= 100) return 'var(--accent-success)';
  if (pct < 70) return 'var(--accent-warning)';
  return 'var(--accent-primary)';
};

const AnalyticsPage = () => {
  const navigate = useNavigate();
  const [fill, setFill] = useState(null);
  const [categories, setCategories] = useState([]);
  const [edits, setEdits] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [fillData, catsData, editsData] = await Promise.all([
        api.getFillAnalytics(),
        api.getCategoryAnalytics(),
        api.getEditAnalytics(days),
      ]);
      setFill(fillData);
      setCategories(catsData.categories || []);
      setEdits(editsData);
    } catch (e) {
      setError(e.message || 'Не удалось загрузить аналитику');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const changeDays = (value) => {
    if (value !== days) setDays(value);
  };

  if (loading && !fill) {
    return (
      <div className="card">
        <div className="loading-spinner">
          <div className="spinner" />
          <p style={{ color: 'var(--text-secondary)' }}>Загрузка...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <div className="alert alert-error">{error}</div>
        <div style={{ marginTop: '1rem' }}>
          <Button variant="outline" onClick={load}>
            <Icon name="refresh" size={16} /> Повторить
          </Button>
        </div>
      </div>
    );
  }

  if (fill && fill.total === 0) {
    return (
      <div className="card">
        <EmptyState
          icon="box"
          title="Аналитика появится после первого импорта"
          description="Импортируйте товары из файла или по API-ключу площадки — и здесь появится заполненность полей, срезы по категориям и история правок."
          actionLabel="Перейти к импорту"
          onAction={() => navigate('/import')}
        />
      </div>
    );
  }

  const fields = [...(fill?.fields || [])].sort((a, b) => {
    if (a.critical !== b.critical) return a.critical ? -1 : 1; // критические выше
    return a.pct - b.pct; // худшие — выше внутри группы
  });

  const byDay = edits?.by_day || [];
  const maxCount = Math.max(1, ...byDay.map((d) => d.count));
  const labelStep = byDay.length > 10 ? Math.ceil(byDay.length / 10) : 1;

  return (
    <div>
      <header className="header">
        <div>
          <h1 className="header-title">Аналитика</h1>
          <p className="header-subtitle">
            Заполненность карточек, срезы по категориям и история правок — по вашим товарам
          </p>
        </div>
        <div className="header-actions">
          <Button variant="outline" onClick={load} disabled={loading} loading={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
        </div>
      </header>

      {/* ==== KPI ==== */}
      <div className="stats-grid" style={{ marginBottom: '1rem' }}>
        <div className="stat-card">
          <div className="stat-value">{fill?.total ?? '—'}</div>
          <div className="stat-label">Товаров</div>
        </div>
        <div className={`stat-card ${fill && fill.ready_pct >= 80 ? 'success' : ''}`}>
          <div className="stat-value">{fill ? `${fill.ready_pct}%` : '—'}</div>
          <div className="stat-label">Готовы к экспорту</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {fill ? `${fill.ready_count} из ${fill.total} товаров` : ''}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{fill ? `${fill.avg_fill_pct}%` : '—'}</div>
          <div className="stat-label">Средняя заполненность</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            по всем полям карточки
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{edits?.total ?? '—'}</div>
          <div className="stat-label">Правок за {days} дн.</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {(edits?.by_action || []).map((a) => `${EDIT_ACTION_LABELS[a.action] || a.action}: ${a.count}`).join(' · ') || 'пока без правок'}
          </div>
        </div>
      </div>

      {/* ==== Заполненность полей ==== */}
      <div className="card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
        <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.5rem' }}>Заполненность полей</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: '0 0 1rem' }}>
          Красное — критичные для экспорта поля (бренд, вес, габариты, НДС, ТН ВЭД…). Худшие —
          сверху: начинайте дозаполнение с них.
        </p>
        {fields.map((f) => (
          <div
            key={f.key}
            style={{
              display: 'grid',
              gridTemplateColumns: '220px 1fr 56px',
              gap: '0.75rem',
              alignItems: 'center',
              padding: '0.35rem 0',
            }}
          >
            <div style={{ fontSize: '0.9rem' }}>
              {f.label}
              {f.critical && (
                <span style={{ color: 'var(--accent-danger)', marginLeft: '0.3rem' }} title="Критичное для экспорта поле">
                  *
                </span>
              )}
            </div>
            <div className="progress-bar-wrapper">
              <div
                className="progress-bar-fill"
                style={{
                  width: `${Math.max(f.pct, 1)}%`,
                  background: fill_color(f.pct, f.critical),
                }}
              />
            </div>
            <div
              style={{
                fontSize: '0.85rem',
                textAlign: 'right',
                color: f.pct >= 100 ? 'var(--text-secondary)' : 'var(--text-primary)',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {f.pct}%
            </div>
          </div>
        ))}
      </div>

      {/* ==== Категории ==== */}
      <div className="card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
        <h2 style={{ fontSize: '1.05rem', margin: '0 0 1rem' }}>Категории</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Категория</th>
                <th>Товаров</th>
                <th>Готовы к экспорту</th>
                <th>Ср. цена</th>
                <th>Ср. заполненность</th>
                <th>Маппинг</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.category}>
                  <td>{c.category}</td>
                  <td>{c.count}</td>
                  <td>
                    {c.ready_count} / {c.count}
                  </td>
                  <td>{c.avg_price ? `${c.avg_price.toLocaleString('ru-RU')} ₽` : '—'}</td>
                  <td>{c.avg_fill_pct}%</td>
                  <td>{c.mapped_pct > 0 ? `${c.mapped_pct}%` : <span className="err-text">не задан</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ==== История правок ==== */}
      <div className="card" style={{ padding: '1.25rem' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
            marginBottom: '1rem',
            flexWrap: 'wrap',
          }}
        >
          <h2 style={{ fontSize: '1.05rem', margin: 0 }}>История правок</h2>
          <div className="import-method-toggle" style={{ margin: 0 }}>
            <button
              className={`toggle-btn ${days === 7 ? 'active' : ''}`}
              onClick={() => changeDays(7)}
            >
              7 дней
            </button>
            <button
              className={`toggle-btn ${days === 30 ? 'active' : ''}`}
              onClick={() => changeDays(30)}
            >
              30 дней
            </button>
          </div>
        </div>

        {byDay.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '3px', height: '110px', marginBottom: '1rem' }}>
            {byDay.map((d, i) => (
              <div
                key={d.date}
                title={`${fmtDay(d.date)}: ${d.count} правок${d.undone ? `, отменено: ${d.undone}` : ''}`}
                style={{
                  flex: 1,
                  minWidth: '4px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'flex-end',
                  alignItems: 'center',
                  gap: '4px',
                  height: '100%',
                }}
              >
                <div
                  style={{
                    width: '100%',
                    minHeight: d.count > 0 ? '4px' : '2px',
                    height: `${Math.round((d.count / maxCount) * 100)}%`,
                    borderRadius: '3px 3px 0 0',
                    background:
                      d.count > 0
                        ? 'linear-gradient(180deg, var(--accent-primary), var(--accent-secondary))'
                        : 'var(--border-color)',
                    opacity: d.count > 0 ? 1 : 0.5,
                  }}
                />
                {i % labelStep === 0 && (
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                    {fmtDay(d.date)}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {(edits?.recent || []).length > 0 ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Когда</th>
                  <th>Действие</th>
                  <th>Описание</th>
                  <th>Товаров</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {(edits?.recent || []).map((r) => (
                  <tr key={r.id}>
                    <td>{fmtDate(r.created_at)}</td>
                    <td>{EDIT_ACTION_LABELS[r.action] || r.action}</td>
                    <td>{r.label || '—'}</td>
                    <td>{r.items}</td>
                    <td>
                      {r.undone ? (
                        <span className="badge badge-pending">отменено</span>
                      ) : (
                        <span className="badge badge-success">применено</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', margin: 0 }}>
            Правок за период не было — здесь появится каждое массовое обновление, подбор ТН ВЭД и
            дозаполнение дефолтами.
          </p>
        )}
      </div>
    </div>
  );
};

export default AnalyticsPage;
