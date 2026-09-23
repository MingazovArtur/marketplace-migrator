import React, { useState, useEffect, useCallback, useRef } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import EmptyState from '../components/common/EmptyState';
import { api } from '../api';

const PLATFORMS = [
  { id: 'ozon', name: 'Ozon', color: '#005bff' },
  { id: 'yandex', name: 'Яндекс Маркет', color: '#fc3f1d' },
  { id: 'wildberries', name: 'Wildberries', color: '#cb11ab' },
];

/* Оценка свежести спека */
const getStaleness = (fetchedAt) => {
  if (!fetchedAt) return { level: 'none', label: 'Не загружено', color: 'var(--text-muted)' };
  const days = Math.floor((Date.now() - new Date(fetchedAt).getTime()) / 86400000);
  if (days <= 7) return { level: 'fresh', label: `Обновлено ${days} дн. назад`, color: 'var(--accent-success)' };
  if (days <= 30) return { level: 'normal', label: `Обновлено ${days} дн. назад`, color: 'var(--accent-warning)' };
  return { level: 'stale', label: `Устарело (${days} дн.)`, color: 'var(--accent-danger)' };
};

const formatDate = (iso) =>
  iso ? new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }) : '—';

const SpecsPage = () => {
  const [platform, setPlatform] = useState('ozon');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showRefreshModal, setShowRefreshModal] = useState(false);
  const [selectedSpec, setSelectedSpec] = useState(null);
  const [refreshLoading, setRefreshLoading] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState('');

  // ✅ Новое: состояние прогресса для фоновой загрузки Ozon
  const [progress, setProgress] = useState(null);
  const pollingRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const d = await api.getSpecs(platform);
      setData(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [platform]);

  useEffect(() => { load(); }, [load]);

  // ✅ Остановка polling при размонтировании компонента
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, []);

  // ✅ Запуск polling прогресса (для Ozon / Celery-задач)
  const startPolling = useCallback((taskId) => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
    }

    pollingRef.current = setInterval(async () => {
      try {
        const p = await api.getSpecsRefreshProgress(platform, taskId);
        setProgress(p);

        if (p.status === 'completed' || p.status === 'failed') {
          clearInterval(pollingRef.current);
          pollingRef.current = null;

          if (p.status === 'completed') {
            setRefreshMessage(
              `✅ Готово: ${p.success || p.done || 0} категорий загружено. Ошибок: ${p.errors || 0}.`
            );
            await load();
          } else if (p.status === 'failed') {
            setRefreshMessage(`❌ Ошибка загрузки: ${p.error || 'неизвестная ошибка'}`);
          }
        }
      } catch (err) {
        // Сбои polling — не ломаем UI, просто пропускаем тик
        console.warn('Polling failed:', err);
      }
    }, 2000);
  }, [platform, load]);

  // ✅ Универсальный закрытие модалки — с остановкой polling
  const handleCloseModal = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setProgress(null);
    setShowRefreshModal(false);
    setRefreshMessage('');
    setRefreshLoading(false);
  };

  // ✅ Обработчик нажатия «Загрузить спеки» в модалке
  const handleRefresh = async (apiKey, businessId) => {
    setRefreshLoading(true);
    setRefreshMessage('');
    setProgress(null);

    try {
      const result = await api.refreshSpecs(platform, apiKey, null, businessId || null);

      // ==================== OZON: фоновая задача через Celery ====================
      if (platform === 'ozon' && result.task_id) {
        setRefreshMessage(
          '🚀 Загрузка запущена в фоне (8000+ категорий, ~20-40 мин). Можете работать — прогресс будет виден здесь.'
        );
        setRefreshLoading(false); // кнопка «Загрузить» больше не нужна
        startPolling(result.task_id);
        return;
      }

      // ==================== YANDEX / WB: синхронный режим ====================
      setRefreshMessage(
        `✅ Загружено категорий: ${result.fetched}. Ошибок: ${result.errors}`
      );
      setShowRefreshModal(false);
      setRefreshLoading(false);
      await load();
    } catch (e) {
      setRefreshMessage(`❌ ${e.message}`);
      setRefreshLoading(false);
    }
  };

  const specs = data?.specs || [];

  return (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">Спецификации площадок</h1>
          <p className="header-subtitle">
            Структуры категорий, атрибуты и словари значений — загружаются через API площадок
          </p>
        </div>
        <div className="header-actions">
          <Button variant="secondary" onClick={load} disabled={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
          <Button onClick={() => setShowRefreshModal(true)}>
            <Icon name="key" size={16} /> Загрузить спеки
          </Button>
        </div>
      </header>

      {/* Переключатель площадок */}
      <div className="products-toolbar">
        {PLATFORMS.map((p) => (
          <Button
            key={p.id}
            variant={platform === p.id ? 'primary' : 'secondary'}
            onClick={() => setPlatform(p.id)}
          >
            {p.name}
          </Button>
        ))}
      </div>

      {error && <div className="alert alert-error"><div>{error}</div></div>}

      {loading && !data && (
        <div className="card">
          <div className="loading-spinner">
            <div className="spinner" />
            <p style={{ color: 'var(--text-secondary)' }}>Загрузка спеков...</p>
          </div>
        </div>
      )}

      {data && specs.length === 0 && (
        <EmptyState
          icon={<Icon name="layers" size={56} />}
          title="Спеки ещё не загружены"
          description={`Загрузите спецификации ${PLATFORMS.find(p => p.id === platform)?.name} через официальный API площадки. Потребуется API-ключ продавца.`}
          actionLabel="Загрузить спеки"
          onAction={() => setShowRefreshModal(true)}
        />
      )}

      {specs.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {specs.map((spec) => {
            const st = getStaleness(spec.fetched_at);
            const attrCount = spec.spec?.attributes?.length || 0;
            const requiredCount = (spec.spec?.attributes || []).filter(a => a.required).length;

            return (
              <div key={spec.id} className="card spec-card" style={{ padding: '1rem 1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
                  <div style={{ flex: 1, minWidth: 200 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                      <span
                        style={{
                          width: 8, height: 8, borderRadius: '50%',
                          background: st.color, display: 'inline-block',
                        }}
                        title={st.label}
                      />
                      <strong style={{ fontSize: '1.05rem' }}>{spec.category_name}</strong>
                    </div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      ID: {spec.category_id}
                      {spec.parent_category_id && ` · родит. ${spec.parent_category_id}`}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '1rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    <div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>АТРИБУТЫ</div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {requiredCount}/{attrCount} <span style={{ fontWeight: 400 }}>обяз.</span>
                      </div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>ЛИСТОВ</div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {spec.spec?.sheets?.length || 0}
                      </div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>СВЕЖЕСТЬ</div>
                      <div style={{ fontWeight: 600, color: st.color }}>
                        {st.level === 'none' ? '—' : st.label}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <Button variant="secondary" size="small" onClick={() => setSelectedSpec(spec)}>
                      <Icon name="tag" size={15} /> Атрибуты
                    </Button>
                  </div>
                </div>

                {st.level === 'stale' && (
                  <div className="form-hint" style={{ color: 'var(--accent-danger)', marginTop: '0.5rem' }}>
                    ⚠️ Спек устарел. Площадка могла изменить структуру — рекомендуем обновить.
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Модалка обновления спеков */}
      {showRefreshModal && (
        <RefreshSpecsModal
          platform={platform}
          loading={refreshLoading}
          message={refreshMessage}
          progress={progress}
          onClose={handleCloseModal}
          onSubmit={handleRefresh}
        />
      )}

      {/* Модалка просмотра атрибутов */}
      {selectedSpec && (
        <SpecDetailModal
          spec={selectedSpec}
          onClose={() => setSelectedSpec(null)}
        />
      )}
    </>
  );
};

/* ========== Модалка обновления спеков ========== */
const RefreshSpecsModal = ({ platform, loading, message, progress, onClose, onSubmit }) => {
  const [apiKey, setApiKey] = useState('');
  const [businessId, setBusinessId] = useState('');
  const [hasServerKey, setHasServerKey] = useState(false);

  const platformInfo = PLATFORMS.find(p => p.id === platform);
  const isOzon = platform === 'ozon';
  const isYandex = platform === 'yandex';
  const isWb = platform === 'wildberries';

  // ✅ Идёт ли фоновая загрузка прямо сейчас
  const isRunning = progress?.status === 'progress' || progress?.status === 'pending';

  // Проверяем наличие серверного ключа в .env
  useEffect(() => {
    if (!isOzon) {
      setHasServerKey(false);
      return;
    }
    let cancelled = false;
    api.getSpecKeySource(platform)
      .then((data) => {
        if (!cancelled) setHasServerKey(!!(data && data.has_server_key));
      })
      .catch(() => {
        if (!cancelled) setHasServerKey(false);
      });
    return () => { cancelled = true; };
  }, [platform, isOzon]);

  // ✅ 1) ozonKeyError объявлен ПЕРВЫМ
  const ozonKeyError = isOzon && apiKey.trim() && !/^\d+\s*:\s*\S+$/.test(apiKey.trim())
    ? 'Неверный формат. Нужно: ЧИСЛО:UUID, например 1234567:e30b97e3-997e-4574-8ddf-56466bcd20b8. Числовой Client ID — в кабинете Ozon → Настройки → API-ключи.'
    : '';

  // ✅ 2) canSubmit — учитывает, что во время polling кнопка должна быть disabled
  const canSubmit = !isRunning && (
    isOzon
      ? ((!!apiKey.trim() && !ozonKeyError) || hasServerKey)
      : isYandex
        ? !!apiKey.trim() && !!businessId.trim()
        : isWb
          ? !!apiKey.trim()
          : false
  );

  const placeholder = isOzon
    ? (hasServerKey
      ? 'Оставьте пустым для использования серверного ключа'
      : '1234567:e30b97e3-997e-4574-8ddf-56466bcd20b8')
    : isYandex
      ? 'OAuth-токен Яндекс Маркета'
      : 'API-ключ WB (категория «Контент»)';

  // ✅ Расчёт процента для прогресс-бара
  const percent = progress?.total
    ? Math.round(((progress.done || 0) * 100) / progress.total)
    : 0;

  return (
    <div className="modal-overlay" onClick={isRunning ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="key" size={22} /> Загрузка спеков {platformInfo?.name}
          </h2>
          <button
            type="button"
            className="close-btn"
            onClick={onClose}
            title="Закрыть"
            disabled={isRunning}
          >
            <Icon name="close" size={16} />
          </button>
        </div>

        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem' }}>
          Мы подтянем структуру категорий и атрибуты через официальный API площадки.
          Ключ используется только для этого запроса и не сохраняется в БД.
        </p>

        {!isOzon && !isYandex && !isWb && (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            <div>Загрузчик для {platformInfo?.name} ещё не реализован.</div>
          </div>
        )}

        {isOzon && hasServerKey && (
          <div className="alert alert-success" style={{ marginBottom: '1rem' }}>
            <div>
              <Icon name="check" size={16} style={{ marginRight: '0.5rem' }} />
              Серверный ключ Ozon настроен в .env — можно загружать спеки без ввода ключа.
            </div>
          </div>
        )}

        <label className="form-label">
          {isOzon ? 'API-ключ Ozon' : isYandex ? 'OAuth-токен Яндекс Маркета' : 'API-ключ'}
        </label>
        <input
          className="form-input"
          type="text"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={placeholder}
          disabled={(!isOzon && !isYandex && !isWb) || loading || isRunning}
        />
        <p className="form-hint">
          {isOzon
            ? <>Формат: <code>ЧИСЛО:UUID</code> — числовой Client ID и API-ключ из ЛК Ozon Seller → Настройки → API-ключи. Не пишите слово «client_id».</>
            : isYandex
              ? <>Токен выдаётся в кабинете продавца Яндекс Маркета (Настройки → Интеграция по API). Формат заголовка: <code>OAuth &lt;token&gt;</code>.</>
              : isWb
                ? <>Ключ категории «Контент»: кабинет WB Partners → Настройки → API-доступ → Контент. Передаётся в заголовке <code>Authorization</code> без схемы.</>
                : '—'}
        </p>

        {ozonKeyError && (
          <div className="alert alert-error" style={{ marginTop: '0.5rem' }}>
            <div>{ozonKeyError}</div>
          </div>
        )}

        {isYandex && (
          <>
            <label className="form-label">Номер кабинета (business_id)</label>
            <input
              className="form-input"
              type="text"
              value={businessId}
              onChange={(e) => setBusinessId(e.target.value)}
              placeholder="1234567"
              disabled={loading || isRunning}
            />
            <p className="form-hint">
              Номер кабинета виден в URL личного кабинета: <code>seller.market.yandex.ru/business/1234567/...</code>
            </p>
          </>
        )}

        {/* ✅ ПРОГРЕСС-БАР фоновой загрузки Ozon */}
        {isRunning && (
          <div style={{
            marginTop: '1rem',
            padding: '0.75rem',
            background: 'var(--bg-secondary)',
            borderRadius: 6,
            border: '1px solid var(--border-color)',
          }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '0.5rem',
              fontSize: '0.9rem',
              fontWeight: 600,
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                Загрузка в фоне
              </span>
              <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
                {percent}%
              </span>
            </div>

            <div style={{
              height: 8,
              background: 'var(--border-light)',
              borderRadius: 4,
              overflow: 'hidden',
              marginBottom: '0.5rem',
            }}>
              <div style={{
                height: '100%',
                width: `${percent}%`,
                background: 'var(--accent-primary)',
                borderRadius: 4,
                transition: 'width 0.3s ease',
              }} />
            </div>

            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Загружено: <strong style={{ color: 'var(--accent-success)' }}>{progress.done || 0}</strong>
              {' '}из <strong>{progress.total || 0}</strong>
              {progress.errors > 0 && (
                <> · Ошибок: <strong style={{ color: 'var(--accent-danger)' }}>{progress.errors}</strong></>
              )}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Можете закрыть окно и работать дальше — прогресс будет идти в фоне
            </div>
          </div>
        )}

        {/* ✅ Успешное завершение */}
        {progress?.status === 'completed' && (
          <div className="alert alert-success" style={{ marginTop: '0.75rem' }}>
            <div>
              ✅ Готово! Загружено <strong>{progress.success || progress.done || 0}</strong> категорий.
              {progress.errors > 0 && <> Ошибок: <strong>{progress.errors}</strong>.</>}
            </div>
          </div>
        )}

        {/* ✅ Ошибка завершения */}
        {progress?.status === 'failed' && (
          <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
            <div>❌ {progress.error || 'Ошибка загрузки спеков'}</div>
          </div>
        )}

        {/* Старые сообщения (для синхронного режима Yandex/WB) */}
        {message && !progress && (
          <div
            className={`alert ${message.startsWith('✅') ? 'alert-success' : message.startsWith('🚀') ? 'alert-info' : 'alert-error'}`}
            style={{ marginTop: '0.75rem' }}
          >
            <div>{message}</div>
          </div>
        )}

        <div className="modal-actions">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={loading && !isRunning}
          >
            {isRunning ? 'Закрыть (загрузка продолжится)' : 'Отмена'}
          </Button>
          <Button
            onClick={() => onSubmit(apiKey, businessId)}
            disabled={!canSubmit || loading}
            loading={loading}
          >
            <Icon name="refresh" size={16} />
            {isOzon ? 'Запустить в фоне' : 'Загрузить спеки'}
          </Button>
        </div>
      </div>
    </div>
  );
};

/* ========== Модалка просмотра атрибутов ========== */
const SpecDetailModal = ({ spec, onClose }) => {
  const [search, setSearch] = useState('');
  const [onlyRequired, setOnlyRequired] = useState(false);

  const attrs = spec.spec?.attributes || [];
  const q = search.trim().toLowerCase();

  const filtered = attrs.filter((a) => {
    if (onlyRequired && !a.required) return false;
    if (q && !a.name.toLowerCase().includes(q) && !a.id.includes(q)) return false;
    return true;
  });

  const requiredCount = attrs.filter(a => a.required).length;

  const typeLabel = (t) => ({
    number: 'Число', text: 'Текст', select: 'Выбор', multiselect: 'Множ. выбор',
  }[t] || t);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="layers" size={22} /> {spec.category_name}
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1rem' }}>
          ID: {spec.category_id} · Обновлён: {formatDate(spec.fetched_at)} · Версия: {spec.version || '—'}
        </div>

        {/* Сводка */}
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
            <div className="validation-num">{attrs.filter(a => a.values && a.values.length > 0).length}</div>
            <div>со словарями</div>
          </div>
          <div className="validation-card">
            <div className="validation-num">{spec.spec?.sheets?.length || 0}</div>
            <div>листов XLS</div>
          </div>
        </div>

        {/* Фильтры */}
        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
          <input
            className="form-input"
            placeholder="Поиск по названию или ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ flex: 1, minWidth: 200 }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
            <input type="checkbox" checked={onlyRequired} onChange={(e) => setOnlyRequired(e.target.checked)} />
            Только обязательные
          </label>
        </div>

        {/* Таблица атрибутов */}
        <div style={{ maxHeight: '50vh', overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 8 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-secondary)', zIndex: 1 }}>
              <tr>
                <th style={{ textAlign: 'left', padding: '0.6rem', borderBottom: '1px solid var(--border-color)' }}>ID</th>
                <th style={{ textAlign: 'left', padding: '0.6rem', borderBottom: '1px solid var(--border-color)' }}>Название</th>
                <th style={{ textAlign: 'left', padding: '0.6rem', borderBottom: '1px solid var(--border-color)' }}>Тип</th>
                <th style={{ textAlign: 'left', padding: '0.6rem', borderBottom: '1px solid var(--border-color)' }}>Группа</th>
                <th style={{ textAlign: 'left', padding: '0.6rem', borderBottom: '1px solid var(--border-color)' }}>Значения</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => (
                <tr key={a.id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                  <td style={{ padding: '0.6rem', color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                    {a.id}
                  </td>
                  <td style={{ padding: '0.6rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      {a.required && <span style={{ color: 'var(--accent-danger)', fontWeight: 700 }} title="Обязательное">*</span>}
                      {a.name}
                    </div>
                  </td>
                  <td style={{ padding: '0.6rem' }}>
                    <span className="badge badge-pending">{typeLabel(a.type)}</span>
                  </td>
                  <td style={{ padding: '0.6rem', color: 'var(--text-secondary)' }}>{a.group}</td>
                  <td style={{ padding: '0.6rem' }}>
                    {a.values && a.values.length > 0 ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', maxWidth: 300 }}>
                        {a.values.slice(0, 3).map((v, i) => (
                          <span key={i} className="attr-chip" style={{ fontSize: '0.75rem' }}>{v}</span>
                        ))}
                        {a.values.length > 3 && (
                          <span className="attr-chip more" style={{ fontSize: '0.75rem' }}>+{a.values.length - 3}</span>
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
                  <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    Ничего не найдено
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>Закрыть</Button>
        </div>
      </div>
    </div>
  );
};

export default SpecsPage;