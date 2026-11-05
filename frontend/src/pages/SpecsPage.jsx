import React, { useState, useEffect, useCallback, useRef } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import EmptyState from '../components/common/EmptyState';
import { api } from '../api';

const PLATFORMS = [
  { id: 'ozon', name: 'Ozon', color: '#005bff' },
  { id: 'yandex', name: 'Яндекс Маркет', color: '#fc3f1d' },
  { id: 'wildberries', name: 'Wildberries', color: '#cb11ab' },
  { id: 'magnit', name: 'Магнит Маркет', color: '#e31235' },
  { id: 'megamarket', name: 'Мегамаркет', color: '#8b3ffd' },
  { id: 'holodilnik', name: 'Холодильник.ру', color: '#0072bc' },
  { id: 'aliexpress', name: 'AliExpress', color: '#ff4747' },
];

/* Оценка свежести спека */
const getStaleness = (fetchedAt) => {
  if (!fetchedAt) return { level: 'none', label: 'Не загружено', color: 'var(--text-muted)' };
  const days = Math.floor((Date.now() - new Date(fetchedAt).getTime()) / 86400000);
  if (days <= 7)
    return { level: 'fresh', label: `Обновлено ${days} дн. назад`, color: 'var(--accent-success)' };
  if (days <= 30)
    return {
      level: 'normal',
      label: `Обновлено ${days} дн. назад`,
      color: 'var(--accent-warning)',
    };
  return { level: 'stale', label: `Устарело (${days} дн.)`, color: 'var(--accent-danger)' };
};

const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';

const SpecsPage = ({ user, onNotify, onOpenMonitor }) => {
  const [platform, setPlatform] = useState('ozon');
  const [isAdmin, setIsAdmin] = useState(user?.role === 'admin');

  // ✅ Лёгкий список — только имена категорий (быстро грузится)
  const [categoryNames, setCategoryNames] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  const [showRefreshModal, setShowRefreshModal] = useState(false);
  const [refreshLoading, setRefreshLoading] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState('');

  // ✅ Полная спека — подгружается лениво по клику «Атрибуты»
  const [selectedSpec, setSelectedSpec] = useState(null);
  const [specLoading, setSpecLoading] = useState(false);
  const [specError, setSpecError] = useState('');

  // ✅ Состояние удаления спеков (для администратора)
  const [deletingKey, setDeletingKey] = useState(null);
  const [clearingAll, setClearingAll] = useState(false);

  // ✅ Состояние прогресса для фоновой загрузки спеков (единое для всех площадок)
  const [progress, setProgress] = useState(null);
  const pollingRef = useRef(null);

  useEffect(() => {
    if (user?.role) {
      setIsAdmin(user.role === 'admin');
      return;
    }
    let cancelled = false;
    api
      .getCurrentUser()
      .then((me) => {
        if (!cancelled) setIsAdmin(me?.role === 'admin');
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user]);

  const notify = useCallback(
    (msg) => {
      if (onNotify) onNotify(msg);
    },
    [onNotify]
  );

  // =====================================================================
  // ✅ ЛЁГКАЯ загрузка: только имена категорий (быстро, ~100 КБ)
  // =====================================================================
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    setCategoryNames([]);
    try {
      const names = await api.getSpecNames(platform);
      if (Array.isArray(names)) {
        const normalized = names.map((n) =>
          typeof n === 'string' ? { category_name: n, fetched_at: null, category_id: null } : n
        );
        setCategoryNames(normalized);
      } else {
        setCategoryNames([]);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [platform]);

  useEffect(() => {
    load();
  }, [load]);

  // =====================================================================
  // ✅ Ленивая загрузка полной спеки по клику «Атрибуты»
  // =====================================================================
  const openSpecDetail = useCallback(
    async (categoryName) => {
      setSpecLoading(true);
      setSpecError('');
      setSelectedSpec(null);
      try {
        const spec = await api.getSpec(platform, categoryName);
        setSelectedSpec(spec);
      } catch (e) {
        setSpecError(e.message);
      } finally {
        setSpecLoading(false);
      }
    },
    [platform]
  );

  // =====================================================================
  // ✅ Удаление одной спеки или всех спеков площадки (только для админа)
  // =====================================================================
  const handleDeleteOne = async (cat) => {
    const key = cat.category_id || cat.category_name;
    if (!key) return;
    if (!window.confirm(`Удалить спецификацию «${cat.category_name}»?`)) return;

    setDeletingKey(key);
    setError('');
    try {
      await api.deleteSpec(platform, key);
      setCategoryNames((prev) =>
        prev.filter((item) => (item.category_id || item.category_name) !== key)
      );
      notify(`✅ Спецификация «${cat.category_name}» удалена`);
    } catch (e) {
      setError(e.message);
      notify(`❌ ${e.message}`);
    } finally {
      setDeletingKey(null);
    }
  };

  const handleDeleteAll = async () => {
    const platformTitle = PLATFORMS.find((p) => p.id === platform)?.name || platform;
    if (
      !window.confirm(
        `Вы уверены, что хотите удалить ВСЕ спецификации (${categoryNames.length} шт.) для площадки «${platformTitle}»?`
      )
    ) {
      return;
    }

    setClearingAll(true);
    setError('');
    try {
      const res = await api.deleteAllSpecs(platform);
      setCategoryNames([]);
      notify(`✅ ${res.message || `Все спецификации ${platformTitle} удалены`}`);
    } catch (e) {
      setError(e.message);
      notify(`❌ ${e.message}`);
    } finally {
      setClearingAll(false);
    }
  };

  // ✅ Остановка polling при размонтировании
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, []);

  // =====================================================================
  // Polling прогресса фоновой загрузки спеков (единый для всех площадок)
  // =====================================================================
  const startPolling = useCallback(
    (taskId) => {
      if (pollingRef.current) clearInterval(pollingRef.current);

      pollingRef.current = setInterval(async () => {
        try {
          const p = await api.getSpecsRefreshProgress(platform, taskId);
          setProgress(p);

          if (p.status === 'completed' || p.status === 'failed' || p.status === 'paused') {
            clearInterval(pollingRef.current);
            pollingRef.current = null;

            if (p.status === 'completed') {
              setRefreshMessage(
                `✅ Готово: ${p.success || p.done || 0} категорий загружено. Ошибок: ${p.errors || 0}.`
              );
              await load();
            } else if (p.status === 'paused') {
              // Загрузку остановил админ со страницы мониторинга; сделанное сохранено,
              // продолжить можно там же без повторного ввода ключа
              setRefreshMessage(
                `⏸ ${p.message || 'Загрузка поставлена на паузу администратором'}. ` +
                  'Продолжить — на странице «Мониторинг спеков» (кнопка «Возобновить»).'
              );
            } else if (p.status === 'failed') {
              setRefreshMessage(`❌ Ошибка загрузки: ${p.error || 'неизвестная ошибка'}`);
            }
          }
        } catch (err) {
          console.warn('Polling failed:', err);
        }
      }, 1500);
    },
    [platform, load]
  );

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

  const handleRefresh = async (apiKey, businessId) => {
    setRefreshLoading(true);
    setRefreshMessage('');
    setProgress(null);

    try {
      // Для Ozon собираем CLIENT_ID:API_KEY из двух полей (если введено раздельно)
      let finalApiKey = (apiKey || '').trim();
      const cleanId = (businessId || '').trim();
      if (platform === 'ozon' && finalApiKey && !finalApiKey.includes(':') && cleanId) {
        finalApiKey = `${cleanId}:${finalApiKey}`;
      }

      const result = await api.refreshSpecs(platform, finalApiKey, null, cleanId || null);

      // Единый фоновый режим через Celery с прогресс-баром (Ozon / Яндекс Маркет / Wildberries)
      if (result.task_id) {
        const platformTitle = PLATFORMS.find((p) => p.id === platform)?.name || platform;
        setRefreshMessage(`🚀 Загрузка спецификаций ${platformTitle} запущена в фоне...`);
        setProgress({ status: 'pending', total: 0, done: 0, success: 0, errors: 0, percent: 0 });
        setRefreshLoading(false);
        startPolling(result.task_id);
        return;
      }

      // Фолбэк на случай синхронного ответа
      setRefreshMessage(
        `✅ Загружено категорий: ${result.fetched ?? 0}. Ошибок: ${result.errors ?? 0}`
      );
      setRefreshLoading(false);
      await load();
    } catch (e) {
      setRefreshMessage(`❌ ${e.message}`);
      setRefreshLoading(false);
    }
  };

  // ✅ Фильтрация по имени (клиентская — список уже на клиенте)
  const q = filter.trim().toLowerCase();
  const filteredNames = q
    ? categoryNames.filter((c) => c.category_name.toLowerCase().includes(q))
    : categoryNames;

  // Показываем первые 200 — дальше пользователь уточняет поиск
  const visibleNames = filteredNames.slice(0, 200);
  const hiddenCount = filteredNames.length - visibleNames.length;

  return (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">Спецификации площадок</h1>
          <p className="header-subtitle">
            Категории, атрибуты и словари значений — загружаются через официальный API площадки
          </p>
        </div>
        <div className="header-actions">
          {isAdmin && onOpenMonitor && (
            <Button variant="outline" onClick={onOpenMonitor} title="Очередь и прогресс всех загрузок спеков">
              <Icon name="report" size={16} /> Мониторинг загрузок
            </Button>
          )}
          <Button variant="secondary" onClick={load} disabled={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
          {isAdmin && categoryNames.length > 0 && (
            <Button
              variant="outline"
              onClick={handleDeleteAll}
              disabled={loading || clearingAll}
              loading={clearingAll}
              style={{ color: 'var(--accent-danger)', borderColor: 'var(--accent-danger)' }}
              title="Удалить все загруженные спецификации текущей площадки"
            >
              <Icon name="trash" size={16} /> Очистить все ({categoryNames.length})
            </Button>
          )}
          <Button onClick={() => setShowRefreshModal(true)}>
            <Icon name="key" size={16} /> Загрузить спеки
          </Button>
        </div>
      </header>

      <div className="products-toolbar" style={{ flexWrap: 'wrap' }}>
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

      {error && (
        <div className="alert alert-error">
          <div>{error}</div>
        </div>
      )}

      {loading && categoryNames.length === 0 && (
        <div className="card">
          <div className="loading-spinner">
            <div className="spinner" />
            <p style={{ color: 'var(--text-secondary)' }}>Загрузка списка категорий...</p>
          </div>
        </div>
      )}

      {categoryNames.length === 0 && !loading && !error && (
        <EmptyState
          icon={<Icon name="layers" size={56} />}
          title="Спеки ещё не загружены"
          description={`Загрузите спецификации ${PLATFORMS.find((p) => p.id === platform)?.name} через официальный API площадки. Потребуется API-ключ продавца.`}
          actionLabel="Загрузить спеки"
          onAction={() => setShowRefreshModal(true)}
        />
      )}

      {categoryNames.length > 0 && (
        <>
          {/* Сводка и поиск */}
          <div className="card" style={{ padding: '1rem 1.25rem', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                Всего категорий:{' '}
                <strong style={{ color: 'var(--text-primary)' }}>{categoryNames.length}</strong>
              </div>
              <input
                className="form-input"
                placeholder="Поиск по названию категории..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                style={{ flex: 1, minWidth: 250 }}
              />
            </div>
          </div>

          {/* Список категорий — лёгкие карточки (без атрибутов) */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {visibleNames.map((cat, idx) => {
              const st = getStaleness(cat.fetched_at);
              const itemKey = cat.category_id || cat.category_name;
              const isDeleting = deletingKey === itemKey;
              return (
                <div
                  key={itemKey || idx}
                  className="card spec-card"
                  style={{ padding: '0.75rem 1.25rem' }}
                >
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}
                  >
                    <div style={{ flex: 1, minWidth: 200 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            background: st.color,
                            display: 'inline-block',
                          }}
                          title={st.label}
                        />
                        <strong style={{ fontSize: '1rem' }}>{cat.category_name}</strong>
                      </div>
                      {cat.category_id && cat.category_id !== cat.category_name && (
                        <div
                          style={{
                            color: 'var(--text-muted)',
                            fontSize: '0.8rem',
                            marginTop: '0.15rem',
                          }}
                        >
                          ID: {cat.category_id}
                        </div>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <Button
                        variant="secondary"
                        size="small"
                        onClick={() => openSpecDetail(itemKey)}
                      >
                        <Icon name="tag" size={15} /> Атрибуты
                      </Button>
                      {isAdmin && (
                        <Button
                          variant="outline"
                          size="small"
                          onClick={() => handleDeleteOne(cat)}
                          disabled={isDeleting}
                          loading={isDeleting}
                          title={`Удалить спецификацию «${cat.category_name}»`}
                          style={{ color: 'var(--accent-danger)' }}
                        >
                          <Icon name="trash" size={15} />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}

            {hiddenCount > 0 && (
              <div
                className="card"
                style={{
                  padding: '1rem',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                  fontSize: '0.9rem',
                }}
              >
                ...и ещё <strong>{hiddenCount}</strong> категорий. Уточните поиск, чтобы увидеть
                больше.
              </div>
            )}

            {visibleNames.length === 0 && q && (
              <div
                className="card"
                style={{
                  padding: '2rem',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                }}
              >
                По запросу «{filter}» ничего не найдено
              </div>
            )}
          </div>
        </>
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

      {/* Модалка просмотра атрибутов (с индикатором загрузки) */}
      {(selectedSpec || specLoading || specError) && (
        <SpecDetailModal
          spec={selectedSpec}
          loading={specLoading}
          error={specError}
          onClose={() => {
            setSelectedSpec(null);
            setSpecError('');
          }}
        />
      )}
    </>
  );
};

/* =====================================================================
   Модалка обновления спеков (ЕДИНЫЙ ФОРМАТ ДЛЯ ВСЕХ ПЛОЩАДОК)
   ===================================================================== */
const RefreshSpecsModal = ({ platform, loading, message, progress, onClose, onSubmit }) => {
  const [businessId, setBusinessId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [hasServerKey, setHasServerKey] = useState(false);

  const platformInfo = PLATFORMS.find((p) => p.id === platform);
  const isOzon = platform === 'ozon';
  const isYandex = platform === 'yandex';
  const isWb = platform === 'wildberries';
  const isSupported = isOzon || isYandex || isWb;

  const isRunning = progress?.status === 'progress' || progress?.status === 'pending';

  useEffect(() => {
    if (!isOzon) {
      setHasServerKey(false);
      return;
    }
    let cancelled = false;
    api
      .getSpecKeySource(platform)
      .then((data) => {
        if (!cancelled) setHasServerKey(!!(data && data.has_server_key));
      })
      .catch(() => {
        if (!cancelled) setHasServerKey(false);
      });
    return () => {
      cancelled = true;
    };
  }, [platform, isOzon]);

  // Если пользователь вставил в одно из полей полный ключ вида "123456:uuid", автоматически разделим его на два поля
  const handleBusinessIdChange = (val) => {
    if (isOzon && val.includes(':')) {
      const [cid, keyPart] = val.split(':', 2);
      setBusinessId(cid.trim());
      if (keyPart && !apiKey) setApiKey(keyPart.trim());
      return;
    }
    setBusinessId(val);
  };

  const handleApiKeyChange = (val) => {
    if (isOzon && val.includes(':') && /^\d+\s*:/.test(val.trim())) {
      const [cid, keyPart] = val.trim().split(':', 2);
      if (!businessId) setBusinessId(cid.trim());
      setApiKey(keyPart.trim());
      return;
    }
    setApiKey(val);
  };

  const cleanId = businessId.trim();
  const cleanKey = apiKey.trim();

  const idFormatError =
    (isOzon || isYandex) && cleanId && !/^\d+$/.test(cleanId)
      ? 'ID кабинета / Client ID должен состоять только из цифр (например: 1234567).'
      : '';

  const canSubmit =
    isSupported &&
    !isRunning &&
    !idFormatError &&
    (isOzon
      ? (!!cleanId && !!cleanKey) || (!cleanId && !cleanKey && hasServerKey)
      : isYandex
        ? !!cleanId && !!cleanKey
        : isWb
          ? !!cleanKey
          : false);

  const percent =
    progress?.percent !== undefined
      ? progress.percent
      : progress?.total
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
            disabled={loading && !isRunning}
          >
            <Icon name="close" size={16} />
          </button>
        </div>

        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem' }}>
          Мы подтянем структуру категорий, характеристики и словари значений через официальный API
          площадки в фоновом режиме. Ключ используется только для этого запроса.
        </p>

        {!isSupported && (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            <div>
              Для площадки «{platformInfo?.name}» используется выгрузка по эталонным XLSX-шаблонам в
              разделе «Шаблоны».
            </div>
          </div>
        )}

        {isOzon && hasServerKey && (
          <div className="alert alert-success" style={{ marginBottom: '1rem' }}>
            <div>
              <Icon name="check" size={16} style={{ marginRight: '0.5rem' }} />
              Серверный ключ Ozon настроен в .env — поля ниже можно оставить пустыми.
            </div>
          </div>
        )}

        {/* Поле 1: Номер кабинета / Client ID (единый формат) */}
        <label className="form-label">
          {isOzon
            ? '1. Номер кабинета (Client ID)'
            : isYandex
              ? '1. Номер кабинета (business_id)'
              : '1. Номер кабинета / ID продавца (необязательно для WB)'}
        </label>
        <input
          className="form-input"
          type="text"
          value={businessId}
          onChange={(e) => handleBusinessIdChange(e.target.value)}
          placeholder={
            isOzon
              ? hasServerKey
                ? 'Оставьте пустым для серверного ключа или введите Client ID (например: 1234567)'
                : 'Например: 1234567'
              : isYandex
                ? 'Например: 12345678'
                : 'Для Wildberries можно оставить пустым'
          }
          disabled={!isSupported || loading || isRunning}
        />
        <p className="form-hint" style={{ marginBottom: '0.85rem' }}>
          {isOzon ? (
            <>
              Числовой <code>Client ID</code> из личного кабинета Ozon Seller → Настройки →
              API-ключи.
            </>
          ) : isYandex ? (
            <>
              Номер бизнеса (<code>business_id</code>) из URL кабинета:{' '}
              <code>seller.market.yandex.ru/business/12345678/...</code>
            </>
          ) : (
            <>Для Wildberries авторизация выполняется по единому токену ниже.</>
          )}
        </p>

        {/* Поле 2: API-ключ / Токен (единый формат) */}
        <label className="form-label">
          {isOzon
            ? '2. API-ключ (API-Key)'
            : isYandex
              ? '2. API-ключ (ACMA:...) или OAuth-токен'
              : '2. API-ключ (токен категории «Контент»)'}
        </label>
        <input
          className="form-input"
          type="text"
          value={apiKey}
          onChange={(e) => handleApiKeyChange(e.target.value)}
          placeholder={
            isOzon
              ? hasServerKey
                ? 'Оставьте пустым для серверного ключа или введите UUID API-Key'
                : 'e30b97e3-997e-4574-8ddf-56466bcd20b8'
              : isYandex
                ? 'ACMA:... или y0_AgAAAA...'
                : 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...'
          }
          disabled={!isSupported || loading || isRunning}
        />
        <p className="form-hint">
          {isOzon ? (
            <>
              Секретный ключ <code>API-Key</code> (формат UUID) из кабинета Ozon Seller → Настройки
              → API-ключи.
            </>
          ) : isYandex ? (
            <>
              Токен выдаётся в кабинете продавца Яндекс Маркета (Настройки → Модули и API).
            </>
          ) : isWb ? (
            <>
              Ключ категории «Контент»: кабинет WB Партнёры → Настройки → Доступ к API.
            </>
          ) : (
            '—'
          )}
        </p>

        {idFormatError && (
          <div className="alert alert-error" style={{ marginTop: '0.5rem' }}>
            <div>{idFormatError}</div>
          </div>
        )}

        {/* Прогресс-бар фоновой загрузки (единый для Ozon, Яндекс Маркета и Wildberries) */}
        {isRunning && (
          <div
            style={{
              marginTop: '1rem',
              padding: '0.85rem 1rem',
              background: 'var(--bg-secondary)',
              borderRadius: 8,
              border: '1px solid var(--border-color)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '0.5rem',
                fontSize: '0.9rem',
                fontWeight: 600,
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                {progress?.total > 0
                  ? `Загрузка спецификаций ${platformInfo?.name} в фоне...`
                  : `Получаем дерево категорий ${platformInfo?.name}...`}
              </span>
              <span style={{ color: 'var(--accent-primary)', fontWeight: 700 }}>{percent}%</span>
            </div>

            <div
              style={{
                height: 8,
                background: 'var(--border-light)',
                borderRadius: 4,
                overflow: 'hidden',
                marginBottom: '0.5rem',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${percent}%`,
                  background: 'var(--accent-primary)',
                  borderRadius: 4,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>

            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Загружено:{' '}
              <strong style={{ color: 'var(--accent-success)' }}>
                {progress.success || progress.done || 0}
              </strong>{' '}
              из <strong>{progress.total || '…'}</strong>
              {progress.errors > 0 && (
                <>
                  {' '}
                  · Ошибок:{' '}
                  <strong style={{ color: 'var(--accent-danger)' }}>{progress.errors}</strong>
                </>
              )}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Вы можете закрыть это окно и продолжить работу — загрузка завершится в фоновом режиме.
            </div>
          </div>
        )}

        {progress?.status === 'completed' && (
          <div className="alert alert-success" style={{ marginTop: '0.75rem' }}>
            <div>
              ✅ Готово! Загружено <strong>{progress.success || progress.done || 0}</strong>{' '}
              категорий ({platformInfo?.name}).
              {progress.errors > 0 && (
                <>
                  {' '}
                  Ошибок: <strong>{progress.errors}</strong>.
                </>
              )}
            </div>
          </div>
        )}

        {progress?.status === 'failed' && (
          <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
            <div>❌ {progress.error || 'Ошибка загрузки спеков'}</div>
          </div>
        )}

        {message && !progress && (
          <div
            className={`alert ${
              message.startsWith('✅')
                ? 'alert-success'
                : message.startsWith('🚀')
                  ? 'alert-info'
                  : 'alert-error'
            }`}
            style={{ marginTop: '0.75rem' }}
          >
            <div>{message}</div>
          </div>
        )}

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={loading && !isRunning}>
            {isRunning ? 'Закрыть (загрузка продолжится)' : 'Отмена'}
          </Button>
          <Button
            onClick={() => onSubmit(cleanKey, cleanId)}
            disabled={!canSubmit || loading || isRunning}
            loading={loading}
          >
            <Icon name="refresh" size={16} /> Запустить в фоне
          </Button>
        </div>
      </div>
    </div>
  );
};

/* =====================================================================
   Модалка просмотра атрибутов (с lazy-loading)
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

export default SpecsPage;