import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../api';

const OP_LABELS = {
  import_file: 'Импорт файла',
  import_api: 'Импорт API',
  import_yml: 'Импорт YML',
  export: 'Экспорт',
  migrate: 'Миграция',
  media_download: 'Скачивание фото',
};

const fmtDuration = (ms) => {
  if (!ms) return '—';
  if (ms < 1000) return `${ms} мс`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} с`;
  return `${Math.floor(s / 60)} мин ${Math.round(s % 60)} с`;
};

const StatsDashboard = () => {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.getDashboardStats(days));
    } catch (e) {
      console.error('Ошибка статистики:', e);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) return <div className="progress-status">⏳ Загрузка статистики...</div>;
  if (!data) return null;

  const maxDay = Math.max(1, ...data.by_day.map(d => d.import + d.export + d.migrate + d.other));

  return (
    <div className="stats-dash">
      <div className="stats-dash-header">
        <h3>📈 Статистика операций</h3>
        <div className="import-method-toggle">
          {[7, 30].map(d => (
            <button
              key={d}
              className={`toggle-btn ${days === d ? 'active' : ''}`}
              onClick={() => setDays(d)}
            >
              {d} дней
            </button>
          ))}
        </div>
      </div>

      {/* KPI */}
      <div className="stats-kpi-row">
        <div className="stat-kpi">
          <div className="stat-kpi-value">{data.totals.operations}</div>
          <div className="stat-kpi-label">операций за {data.period_days} дн.</div>
        </div>
        <div className="stat-kpi ok">
          <div className="stat-kpi-value">{data.success_rate}%</div>
          <div className="stat-kpi-label">успешных операций</div>
        </div>
        <div className="stat-kpi">
          <div className="stat-kpi-value">{fmtDuration(data.avg_duration_ms)}</div>
          <div className="stat-kpi-label">среднее время</div>
        </div>
        <div className="stat-kpi err">
          <div className="stat-kpi-value">{data.totals.error}</div>
          <div className="stat-kpi-label">ошибок</div>
        </div>
      </div>

      {/* График по дням */}
      <div className="chart-card">
        <h4>Активность по дням</h4>
        <div className="bar-chart">
          {data.by_day.map(d => {
            const total = d.import + d.export + d.migrate + d.other;
            const h = Math.round((total / maxDay) * 100);
            return (
              <div
                key={d.date}
                className="bar-col"
                title={`${d.date} · импорт: ${d.import}, экспорт: ${d.export}, миграции: ${d.migrate}, прочее: ${d.other}, ошибок: ${d.error}`}
              >
                <div className="bar-stack" style={{ height: `${Math.max(h, 3)}%` }}>
                  {d.import > 0 && <div className="bar-seg imp" style={{ flexGrow: d.import }} />}
                  {d.export > 0 && <div className="bar-seg exp" style={{ flexGrow: d.export }} />}
                  {d.migrate > 0 && <div className="bar-seg mig" style={{ flexGrow: d.migrate }} />}
                  {d.other > 0 && <div className="bar-seg oth" style={{ flexGrow: d.other }} />}
                </div>
                <div className="bar-label">{d.date.slice(5)}</div>
              </div>
            );
          })}
        </div>
        <div className="chart-legend">
          <span><i className="dot imp" /> Импорт</span>
          <span><i className="dot exp" /> Экспорт</span>
          <span><i className="dot mig" /> Миграции</span>
          <span><i className="dot oth" /> Прочее</span>
        </div>
      </div>

      {/* По типам операций */}
      {data.by_operation.length > 0 && (
        <div className="chart-card">
          <h4>По типам операций</h4>
          <table className="stats-table">
            <thead>
              <tr><th>Операция</th><th>Кол-во</th><th>Успешно</th><th>Ошибки</th><th>Обработано элементов</th></tr>
            </thead>
            <tbody>
              {data.by_operation.map(r => (
                <tr key={r.operation}>
                  <td>{OP_LABELS[r.operation] || r.operation}</td>
                  <td>{r.count}</td>
                  <td className="ok-text">{r.success}</td>
                  <td className={r.error ? 'err-text' : ''}>{r.error}</td>
                  <td>{r.items}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* По площадкам */}
      {data.by_platform.length > 0 && (
        <div className="chart-card">
          <h4>По площадкам</h4>
          <table className="stats-table">
            <thead>
              <tr><th>Площадка</th><th>Операций</th><th>Элементов</th></tr>
            </thead>
            <tbody>
              {data.by_platform.map(r => (
                <tr key={r.platform}>
                  <td>{r.platform}</td>
                  <td>{r.count}</td>
                  <td>{r.items}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default StatsDashboard;