import React, { useState, useEffect, useRef } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';

const normalize = (p) => {
  const total = p?.total ?? 0;
  const done = p?.done ?? p?.processed ?? (p?.status === 'completed' ? total : 0) ?? 0;
  return {
    status: p?.status ?? 'pending',
    total,
    done,
    success: p?.success ?? 0,
    errors: p?.errors ?? 0,
    percent: p?.percent ?? (total ? Math.round((done / total) * 100) : 0),
    error: p?.error || '',
  };
};

const isFinished = (n) =>
  n.status === 'completed' ||
  n.status === 'finished' ||
  n.status === 'failed' ||
  (n.total > 0 && n.done >= n.total);

const BatchMigrateModal = ({
  isOpen,
  onClose,
  selectedIds,
  products,
  onStartMigration,
  pollProgress,
  loading,
  onAutoExport,
}) => {
  const [platform, setPlatform] = useState('ozon');
  const [autoExport, setAutoExport] = useState(true);
  const [batch, setBatch] = useState(null);
  const [prog, setProg] = useState(null);
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const exportedRef = useRef(false);

  useEffect(() => {
    if (isOpen) {
      setBatch(null);
      setProg(null);
      setFinished(false);
      setError('');
      setStarting(false);
      setAutoExport(true);
      exportedRef.current = false;
    }
  }, [isOpen]);

  /* Поллинг прогресса */
  useEffect(() => {
    const batchId = batch?.batch_id || batch?.id;
    if (!batchId || finished) return undefined;

    const timer = setInterval(async () => {
      try {
        const raw = await pollProgress(batchId);
        const n = normalize(raw);
        setProg(n);
        if (n.error) setError(n.error);

        if (isFinished(n)) {
          setFinished(true);
          if (n.status !== 'failed' && autoExport && !exportedRef.current && onAutoExport) {
            exportedRef.current = true;
            onAutoExport(platform);
          }
        }
      } catch (e) {
        setError('Ошибка опроса прогресса: ' + e.message);
      }
    }, 1500);

    return () => clearInterval(timer);
  }, [batch, finished, autoExport, platform, pollProgress, onAutoExport]);

  if (!isOpen) return null;

  /* ✅ Запуск: ошибка остаётся ВНУТРИ модалки, окно не закрывается */
  const handleStart = async () => {
    setError('');
    setStarting(true);
    try {
      const res = await onStartMigration(selectedIds, platform);
      const batchId = res?.batch_id || res?.task_id || res?.id;
      if (!batchId) throw new Error('Сервер не вернул ID задачи (batch_id)');
      setBatch({ batch_id: batchId, total: res?.total ?? selectedIds.length });
    } catch (e) {
      setError(e.message || 'Не удалось запустить пакетную миграцию');
    } finally {
      setStarting(false);
    }
  };

  const n = prog || { total: selectedIds.length, done: 0, success: 0, errors: 0, percent: 0 };
  const percent = Math.min(100, n.percent || 0);

  const stats = (
    <div className="progress-stats">
      <div className="stat-item">
        <div className="stat-label">Всего</div>
        <div className="stat-value">{n.total}</div>
      </div>
      <div className="stat-item">
        <div className="stat-label">Готово</div>
        <div className="stat-value">{n.done}</div>
      </div>
      <div className="stat-item">
        <div className="stat-label">Успешно</div>
        <div className="stat-value success-text">{n.success}</div>
      </div>
      <div className="stat-item">
        <div className="stat-label">Ошибки</div>
        <div className="stat-value error-text">{n.errors}</div>
      </div>
    </div>
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="migrate" size={22} /> Пакетная миграция ({selectedIds.length})
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        {/* Шаг 1: параметры */}
        {!batch && (
          <>
            <label className="form-label">Целевая площадка:</label>
            <div className="platform-selector">
              {PLATFORMS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`platform-btn ${platform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => setPlatform(p.id)}
                >
                  {p.name}
                </button>
              ))}
            </div>

            <label className="bulk-check">
              <input
                type="checkbox"
                checked={autoExport}
                onChange={(e) => setAutoExport(e.target.checked)}
              />
              После завершения сразу скачать файл для кабинета {platform}
            </label>

            {error && (
              <div className="alert alert-error">
                <div>{error}</div>
              </div>
            )}

            <div className="modal-actions">
              <Button variant="outline" onClick={onClose}>
                Отмена
              </Button>
              <Button
                onClick={handleStart}
                disabled={starting || loading}
                loading={starting || loading}
              >
                <Icon name="migrate" size={16} /> Запустить перенос
              </Button>
            </div>
          </>
        )}

        {/* Шаг 2: прогресс */}
        {batch && !finished && (
          <>
            <div className="progress-bar-wrapper">
              <div className="progress-bar-fill" style={{ width: `${percent}%` }} />
              <span className="progress-bar-text">{percent}%</span>
            </div>
            {stats}
            {error && (
              <div className="alert alert-error">
                <div>{error}</div>
              </div>
            )}
            <p className="progress-status">
              Переносим карточки… окно можно закрыть — процесс продолжится на сервере.
            </p>
          </>
        )}

        {/* Шаг 3: финал */}
        {finished && (
          <>
            {stats}
            <p
              className={n.status === 'failed' ? 'error-text' : 'success-text'}
              style={{ textAlign: 'center', margin: '1rem 0' }}
            >
              {n.status === 'failed'
                ? `Пакетная миграция завершилась с ошибкой: ${n.error}`
                : 'Пакетная миграция завершена.'}
            </p>
            <div className="modal-actions">
              {n.status !== 'failed' && (
                <Button variant="outline" onClick={() => onAutoExport && onAutoExport(platform)}>
                  <Icon name="export" size={16} /> Скачать файл для кабинета
                </Button>
              )}
              <Button onClick={onClose}>Готово</Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default BatchMigrateModal;
