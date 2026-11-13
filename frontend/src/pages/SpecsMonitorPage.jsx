import React, { useState, useEffect, useCallback } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import { api } from '../api';
import { PLATFORMS } from '../utils/platformUtils';

const platformName = (id) => PLATFORMS.find((p) => p.id === id)?.name || id || '—';

const fmtTime = (ts) => {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

const fmtElapsed = (fromTs, nowTs) => {
  if (!fromTs) return '—';
  const sec = Math.max(0, Math.round(nowTs - fromTs));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m} мин ${s} с` : `${s} с`;
};

const fmtDuration = (ms) => {
  if (ms == null) return '—';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec} с`;
  return `${Math.floor(sec / 60)} мин ${sec % 60} с`;
};

const fmtDate = (ts) =>
  ts
    ? new Date(ts * 1000).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';

/* ==================== Бейджи состояний ==================== */

const StateBadge = ({ t }) => {
  if (t.pause_requested)
    return (
      <span className="badge badge-pending">
        <Icon name="info" size={14} /> останавливается…
      </span>
    );
  if (t.state === 'queued')
    return (
      <span className="badge badge-pending">
        <Icon name="info" size={14} /> в очереди
      </span>
    );
  if (t.stale)
    return (
      <span className="badge badge-error">
        <Icon name="alert" size={14} /> нет прогресса
      </span>
    );
  return (
    <span className="badge badge-processing">
      <Icon name="refresh" size={14} /> выполняется
    </span>
  );
};

const StatusBadge = ({ s }) => {
  if (s === 'success')
    return (
      <span className="badge badge-success">
        <Icon name="check" size={14} /> успех
      </span>
    );
  if (s === 'partial')
    return (
      <span className="badge badge-pending">
        <Icon name="alert" size={14} /> с ошибками
      </span>
    );
  if (s === 'paused')
    return (
      <span className="badge badge-pending">
        <Icon name="info" size={14} /> на паузе
      </span>
    );
  if (s === 'interrupted')
    return (
      <span className="badge badge-pending">
        <Icon name="alert" size={14} /> прервана
      </span>
    );
  if (s === 'resumed')
    return (
      <span className="badge badge-processing">
        <Icon name="refresh" size={14} /> продолжена
      </span>
    );
  return (
    <span className="badge badge-error">
      <Icon name="alert" size={14} /> ошибка
    </span>
  );
};

/* ==================== Карточка активной загрузки ==================== */

const ActiveTaskCard = ({ t, nowTs, onPause, busy }) => {
  const percent = t.percent || 0;
  return (
    <div className="card" style={{ padding: '0.9rem 1.1rem', marginBottom: '0.6rem' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          flexWrap: 'wrap',
          fontSize: '0.9rem',
        }}
      >
        <strong style={{ minWidth: 110 }}>{platformName(t.platform)}</strong>
        <StateBadge t={t} />
        <span style={{ color: 'var(--text-muted)' }}>
          пользователь:{' '}
          <strong style={{ color: 'var(--text-primary)' }}>{t.username || t.user_id}</strong>
        </span>
        <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: '0.82rem' }}>
          в очереди с {fmtTime(t.enqueued_at)}
          {t.state !== 'queued'
            ? ` · выполняется ${fmtElapsed(t.started_at || t.enqueued_at, nowTs)}`
            : ''}
        </span>
        {t.can_pause && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => onPause(t.task_id)}
            style={{ fontSize: '0.8rem', padding: '0.3rem 0.7rem' }}
          >
            <Icon name="info" size={14} /> Пауза
          </Button>
        )}
      </div>

      {t.state !== 'queued' && (
        <div style={{ marginTop: '0.55rem' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '0.82rem',
              color: 'var(--text-secondary)',
              marginBottom: '0.25rem',
            }}
          >
            <span>
              обработано {t.success + t.errors} из {t.total || '?'} · успешно {t.success} · ошибок{' '}
              {t.errors}
            </span>
            <span>{percent}%</span>
          </div>
          <div
            style={{
              height: 6,
              background: 'var(--bg-secondary)',
              borderRadius: 3,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${percent}%`,
                height: '100%',
                background: t.stale ? 'var(--accent-danger)' : 'var(--primary, #3b82f6)',
                transition: 'width 0.3s',
              }}
            />
          </div>
        </div>
      )}

      {t.pause_requested && (
        <div
          className="alert alert-error"
          style={{ marginTop: '0.55rem', padding: '0.4rem 0.7rem', fontSize: '0.82rem' }}
        >
          <div>
            ⏸ Пауза запрошена: задача остановится после текущего блока категорий (обычно до пары
            минут), сделанное уже сохранено в БД. После остановки карточка перейдёт в секцию «На
            паузе».
          </div>
        </div>
      )}

      {t.stale && (
        <div
          className="alert alert-error"
          style={{ marginTop: '0.55rem', padding: '0.4rem 0.7rem', fontSize: '0.82rem' }}
        >
          <div>
            ⚠️ Задача выполняется без прогресса дольше 15 минут — вероятно, воркер был перезапущен.
            Перезапустите загрузку спеков.
          </div>
        </div>
      )}
    </div>
  );
};

/* ==================== Страница ==================== */

const SpecsMonitorPage = ({ user }) => {
  const isAdmin = user?.role === 'admin';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [paused, setPaused] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getAdminSpecsTasks();
      setData(res);
      setError('');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // ✅ Round 8: живые снимки — SSE-поток (сервер пушит при изменении),
  // polling — автоматический резерв внутри api/sse.js. Кнопка паузы
  // останавливает и поток: переключение paused перезапускает эффект.
  useEffect(() => {
    if (!isAdmin || paused) return undefined;

    const ac = new AbortController();
    setLoading(true); // спиннер до первого снимка (поток шлёт его мгновенно)
    api
      .streamAdminSpecsTasks({
        onUpdate: (res) => {
          setLoading(false);
          setData(res);
          setError('');
        },
        onError: (e) => {
          setLoading(false);
          setError(e.message);
        },
        signal: ac.signal,
      })
      .catch(() => {
        /* поток отменён (пауза/unmount) или закрыт навсегда — молча */
      });

    return () => ac.abort();
  }, [isAdmin, paused]);

  const handlePause = useCallback(
    async (taskId) => {
      setBusyId(taskId);
      setError('');
      setNotice('');
      try {
        const res = await api.pauseSpecsTask(taskId);
        setNotice(res.message || 'Пауза запрошена');
        await load();
      } catch (e) {
        setError(e.message);
      } finally {
        setBusyId(null);
      }
    },
    [load]
  );

  const handleResume = useCallback(
    async (taskId) => {
      setBusyId(taskId);
      setError('');
      setNotice('');
      try {
        const res = await api.resumeSpecsTask(taskId);
        setNotice(res.message || 'Загрузка продолжена');
        await load();
      } catch (e) {
        setError(e.message);
      } finally {
        setBusyId(null);
      }
    },
    [load]
  );

  if (!isAdmin) {
    return (
      <>
        <header className="header">
          <div>
            <h1 className="header-title">Мониторинг загрузки спеков</h1>
          </div>
        </header>
        <div className="alert alert-error">
          <div>Доступ только для администратора.</div>
        </div>
      </>
    );
  }

  const active = data?.active || [];
  const history = data?.history || [];
  // Возобновляемые: «на паузе» и «прерванные» (перезапуск воркера) — выносим
  // в отдельную секцию, чтобы состояние было видно сразу, без поиска в истории
  const resumable = history.filter((t) => t.can_resume);
  const finished = history.filter((t) => !t.can_resume);
  const nowTs = Date.now() / 1000;

  return (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">Мониторинг загрузки спеков</h1>
          <p className="header-subtitle">
            Очередь и ход загрузки спецификаций площадок. Обновляется каждые 3 с. «Пауза» на
            карточке останавливает выбранную загрузку после текущего блока категорий, «Возобновить»
            продолжает с места остановки (ключ API не запрашивается заново).
          </p>
        </div>
        <div className="header-actions">
          <Button variant="secondary" onClick={load} disabled={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
          <Button
            variant="outline"
            onClick={() => setPaused((p) => !p)}
            title="Включает/выключает автодобновление данных на странице. На сами загрузки не влияет — их останавливает кнопка «Пауза» на карточке загрузки."
          >
            <Icon name={paused ? 'refresh' : 'info'} size={16} /> Автодобновление:{' '}
            {paused ? 'выкл' : 'вкл'}
          </Button>
        </div>
      </header>

      {error && (
        <div className="alert alert-error">
          <div>{error}</div>
        </div>
      )}

      {notice && (
        <div
          className="alert alert-success"
          style={{ background: 'var(--accent-success-bg, rgba(34,197,94,0.12))' }}
        >
          <div>{notice}</div>
        </div>
      )}

      {/* Активные */}
      <section style={{ marginTop: '1rem' }}>
        <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.6rem' }}>
          Активные загрузки ({active.length})
          {active.length > 0 && (
            <span
              style={{ color: 'var(--accent-warning)', fontSize: '0.85rem', marginLeft: '0.5rem' }}
            >
              {active.filter((t) => t.state === 'queued').length} в очереди
            </span>
          )}
        </h2>

        {active.length === 0 ? (
          <div className="card" style={{ padding: '1rem 1.1rem', color: 'var(--text-muted)' }}>
            Сейчас ничего не загружается. Запустите загрузку на странице «Спецификации» — задача
            появится здесь сразу (в том числе стоящая в очереди за другой).
          </div>
        ) : (
          active.map((t) => (
            <ActiveTaskCard
              key={t.task_id}
              t={t}
              nowTs={nowTs}
              onPause={handlePause}
              busy={busyId === t.task_id}
            />
          ))
        )}
      </section>

      {/* На паузе / прерваны — возобновление конкретной загрузки */}
      {resumable.length > 0 && (
        <section style={{ marginTop: '1.5rem' }}>
          <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.6rem' }}>
            ⏸ На паузе / прерваны ({resumable.length})
          </h2>
          {resumable.map((t) => (
            <div
              key={t.task_id}
              className="card"
              style={{
                padding: '0.9rem 1.1rem',
                marginBottom: '0.6rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                flexWrap: 'wrap',
                fontSize: '0.9rem',
              }}
            >
              <strong style={{ minWidth: 110 }}>{platformName(t.platform)}</strong>
              <StatusBadge s={t.status} />
              <span style={{ color: 'var(--text-muted)' }}>
                пользователь:{' '}
                <strong style={{ color: 'var(--text-primary)' }}>{t.username || t.user_id}</strong>
              </span>
              <span style={{ color: 'var(--text-muted)' }}>
                категорий сохранено:{' '}
                <strong style={{ color: 'var(--text-primary)' }}>{t.success ?? 0}</strong>
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                {t.status === 'interrupted' ? 'прервана' : 'остановлена'} {fmtDate(t.finished_at)}
              </span>
              <Button
                variant="outline"
                disabled={busyId === t.task_id}
                onClick={() => handleResume(t.task_id)}
                style={{ marginLeft: 'auto', fontSize: '0.8rem', padding: '0.3rem 0.7rem' }}
              >
                <Icon name="refresh" size={14} /> Возобновить
              </Button>
            </div>
          ))}
          <p className="form-hint" style={{ marginTop: '0.4rem' }}>
            Возобновление продолжает загрузку с места остановки: уже сохранённые категории
            пропускаются. «Прервана» — воркер был перезапущен (например, docker compose down):
            прогресс в БД сохранён.
          </p>
        </section>
      )}

      {/* История */}
      <section style={{ marginTop: '1.5rem' }}>
        <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.6rem' }}>
          Последние завершённые ({finished.length})
        </h2>

        {finished.length === 0 ? (
          <div className="card" style={{ padding: '1rem 1.1rem', color: 'var(--text-muted)' }}>
            Завершённых загрузок пока нет (история ведётся с момента установки обновления).
          </div>
        ) : (
          <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '0.6rem 0.9rem', fontWeight: 600 }}>Завершена</th>
                  <th style={{ padding: '0.6rem 0.9rem', fontWeight: 600 }}>Площадка</th>
                  <th style={{ padding: '0.6rem 0.9rem', fontWeight: 600 }}>Пользователь</th>
                  <th style={{ padding: '0.6rem 0.9rem', fontWeight: 600 }}>Итог</th>
                  <th style={{ padding: '0.6rem 0.9rem', fontWeight: 600 }}>Категорий</th>
                  <th style={{ padding: '0.6rem 0.9rem', fontWeight: 600 }}>Ошибок</th>
                  <th style={{ padding: '0.6rem 0.9rem', fontWeight: 600 }}>Длительность</th>
                  <th style={{ padding: '0.6rem 0.9rem', fontWeight: 600 }}></th>
                </tr>
              </thead>
              <tbody>
                {finished.map((t) => (
                  <tr key={t.task_id} style={{ borderTop: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.55rem 0.9rem', whiteSpace: 'nowrap' }}>
                      {fmtDate(t.finished_at)}
                    </td>
                    <td style={{ padding: '0.55rem 0.9rem' }}>{platformName(t.platform)}</td>
                    <td style={{ padding: '0.55rem 0.9rem' }}>{t.username || t.user_id || '—'}</td>
                    <td style={{ padding: '0.55rem 0.9rem' }}>
                      <StatusBadge s={t.status} />
                      {t.resumed_as && (
                        <div
                          style={{
                            fontSize: '0.72rem',
                            color: 'var(--text-muted)',
                            marginTop: '0.2rem',
                          }}
                        >
                          продолжена
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '0.55rem 0.9rem' }}>{t.success ?? '—'}</td>
                    <td style={{ padding: '0.55rem 0.9rem' }}>{t.errors ?? '—'}</td>
                    <td style={{ padding: '0.55rem 0.9rem', whiteSpace: 'nowrap' }}>
                      {fmtDuration(t.duration_ms)}
                    </td>
                    <td style={{ padding: '0.55rem 0.9rem', whiteSpace: 'nowrap' }}>
                      {t.can_resume ? (
                        <Button
                          variant="outline"
                          disabled={busyId === t.task_id}
                          onClick={() => handleResume(t.task_id)}
                          style={{ fontSize: '0.8rem', padding: '0.3rem 0.7rem' }}
                        >
                          <Icon name="refresh" size={14} /> Возобновить
                        </Button>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="form-hint" style={{ marginTop: '0.9rem' }}>
        Загрузки спеков идут в отдельном воркере и не мешают миграциям и выгрузкам. Спеки одной
        площадки грузятся по очереди: вторая и последующие задачи стоят в очереди и стартуют
        автоматически после текущей. «Пауза» останавливает выбранную загрузку после текущего блока
        категорий (сделанное сохранено в БД, ключ не запрашивается заново), «Возобновить» продолжает
        с места остановки. Если задача помечена «прервана» (воркер перезапущен, например docker
        compose down) — её тоже можно продолжить той же кнопкой, прогресс в БД сохранён.
      </p>
    </>
  );
};

export default SpecsMonitorPage;
