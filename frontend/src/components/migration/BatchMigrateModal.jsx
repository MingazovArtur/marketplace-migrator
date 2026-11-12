import React, { useState, useEffect, useRef, useCallback } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { api } from '../../api';

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
  onStartMigration,
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

  // ✅ v4: профили миграции (площадка + дефолты)
  const [profiles, setProfiles] = useState([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [profileMsg, setProfileMsg] = useState('');
  const [profileBusy, setProfileBusy] = useState(false);
  const [showSaveProfile, setShowSaveProfile] = useState(false);
  const [newProfileName, setNewProfileName] = useState('');

  // Загрузка профилей при открытии
  useEffect(() => {
    if (!isOpen) return;
    setProfiles([]);
    setSelectedProfileId('');
    setProfileMsg('');
    setShowSaveProfile(false);
    setNewProfileName('');
    api
      .getMigrationProfiles()
      .then((d) => setProfiles(d.profiles || []))
      .catch(() => setProfiles([]));
  }, [isOpen]);

  const applyProfile = useCallback(async (id) => {
    if (!id) {
      setSelectedProfileId('');
      setProfileMsg('');
      return;
    }
    setProfileBusy(true);
    setProfileMsg('');
    try {
      const res = await api.applyMigrationProfile(id);
      setPlatform(res.platform);
      setSelectedProfileId(id);
      const filled = Object.entries(res.defaults || {}).filter(([, v]) => v != null).length;
      setProfileMsg(
        `Профиль применён: площадка ${res.platform}, дефолтов задано ${filled}. ` +
          'Пустые поля товаров дозаполнит миграция.'
      );
    } catch (e) {
      setProfileMsg('Не удалось применить профиль: ' + e.message);
    } finally {
      setProfileBusy(false);
    }
  }, []);

  const saveProfile = useCallback(async () => {
    const name = newProfileName.trim();
    if (!name) return;
    setProfileBusy(true);
    try {
      const res = await api.saveMigrationProfile({ name, platform });
      setProfiles((prev) => {
        const rest = prev.filter((p) => p.name !== name);
        return [...rest, res.profile].sort((a, b) => a.name.localeCompare(b.name));
      });
      setSelectedProfileId(res.profile.id);
      setShowSaveProfile(false);
      setNewProfileName('');
      setProfileMsg(
        res.created
          ? 'Профиль создан: текущая площадка + ваши глобальные дефолты.'
          : 'Профиль обновлён.'
      );
    } catch (e) {
      setProfileMsg('Не удалось сохранить профиль: ' + e.message);
    } finally {
      setProfileBusy(false);
    }
  }, [newProfileName, platform]);

  const removeProfile = useCallback(
    async (id) => {
      setProfileBusy(true);
      try {
        await api.deleteMigrationProfile(id);
        setProfiles((prev) => prev.filter((p) => p.id !== id));
        if (selectedProfileId === id) setSelectedProfileId('');
      } catch (e) {
        setProfileMsg('Не удалось удалить профиль: ' + e.message);
      } finally {
        setProfileBusy(false);
      }
    },
    [selectedProfileId]
  );

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

  /* ✅ Round 8: прогресс пакетной миграции — SSE-поток (кадры пушем),
   * polling — автоматический резерв внутри api/sse.js */
  useEffect(() => {
    const batchId = batch?.batch_id || batch?.id;
    if (!batchId || finished) return undefined;

    const ac = new AbortController();
    const onUpdate = (raw) => {
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
    };

    api
      .streamTaskProgress(batchId, {
        onUpdate,
        onError: (e) => setError(`Связь с сервером: ${e.message} (продолжаем пробовать)`),
        timeoutMs: 30 * 60 * 1000,
        timeoutMessage: 'Таймаут ожидания пакетной миграции (30 мин). Проверьте логи Celery.',
        pollIntervalMs: 1500,
        signal: ac.signal,
      })
      .catch((e) => {
        if (!ac.signal.aborted) setError('Ошибка отслеживания прогресса: ' + e.message);
      });

    return () => ac.abort();
  }, [batch, finished, autoExport, platform, onAutoExport]);

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
            {/* ✅ v4: быстрый старт по профилю */}
            <div className="card" style={{ padding: '0.8rem 1rem', marginBottom: '0.9rem' }}>
              <h4
                style={{
                  margin: '0 0 0.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                }}
              >
                <Icon name="migrate" size={16} /> Профиль миграции
              </h4>
              <div
                style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}
              >
                <select
                  className="form-input"
                  style={{ maxWidth: 260 }}
                  value={selectedProfileId}
                  onChange={(e) => applyProfile(e.target.value)}
                  disabled={profileBusy}
                >
                  <option value="">— без профиля —</option>
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} → {p.platform}
                    </option>
                  ))}
                </select>
                {selectedProfileId && (
                  <Button
                    variant="outline"
                    size="small"
                    onClick={() => removeProfile(selectedProfileId)}
                    disabled={profileBusy}
                    title="Удалить выбранный профиль"
                  >
                    <Icon name="trash" size={14} />
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="small"
                  onClick={() => setShowSaveProfile((s) => !s)}
                  disabled={profileBusy}
                  title="Сохранить текущую площадку + ваши глобальные дефолты как профиль"
                >
                  <Icon name="template" size={14} /> Сохранить как профиль
                </Button>
              </div>
              {showSaveProfile && (
                <div
                  style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}
                >
                  <input
                    className="form-input"
                    style={{ maxWidth: 260 }}
                    type="text"
                    placeholder="Название профиля (например: Распродажа на Ozon)"
                    value={newProfileName}
                    onChange={(e) => setNewProfileName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && saveProfile()}
                  />
                  <Button
                    size="small"
                    onClick={saveProfile}
                    disabled={profileBusy || !newProfileName.trim()}
                  >
                    Сохранить
                  </Button>
                </div>
              )}
              {profileMsg && (
                <p
                  style={{
                    margin: '0.5rem 0 0',
                    color: 'var(--text-secondary)',
                    fontSize: '0.8rem',
                  }}
                >
                  {profileMsg}
                </p>
              )}
            </div>

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
