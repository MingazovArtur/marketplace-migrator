import React, { useState, useEffect, useCallback, useRef } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import EmptyState from '../components/common/EmptyState';
import { api } from '../api';
import { PLATFORMS } from '../utils/platformUtils';
import RefreshSpecsModal from '../components/specs/RefreshSpecsModal';
import SpecDetailModal from '../components/specs/SpecDetailModal';
import CategoryCard from '../components/specs/CategoryCard';

/* Страница «Спецификации площадок».
 *
 * Р3: монолит SpecsPage.jsx (1115 строк) разбит на
 * components/specs/{RefreshSpecsModal, SpecDetailModal, CategoryCard, specsUtils};
 * здесь осталась только оркестрация: состояние, загрузка списков, polling и layout.
 * Логика и разметка вынесены без изменений.
 */
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
  const trackAbortRef = useRef(null); // отмена SSE-потока прогресса (Round 8)

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

  // ✅ Round 8: отмена SSE-потока прогресса при размонтировании
  useEffect(() => {
    return () => {
      trackAbortRef.current?.abort();
    };
  }, []);

  // =====================================================================
  // Прогресс фоновой загрузки спеков: SSE-поток (Round 8), polling — резерв
  // =====================================================================
  const trackRefresh = useCallback(
    (taskId) => {
      trackAbortRef.current?.abort();
      const ac = new AbortController();
      trackAbortRef.current = ac;

      api
        .streamSpecsRefresh(platform, taskId, {
          onUpdate: (p) => {
            setProgress(p);

            if (p.status === 'completed') {
              setRefreshMessage(
                `✅ Готово: ${p.success || p.done || 0} категорий загружено. Ошибок: ${p.errors || 0}.`
              );
              load();
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
          },
          timeoutMs: 30 * 60 * 1000,
          signal: ac.signal,
        })
        .catch(() => {
          /* таймаут/отмена: прогресс-бар уже показывает последнее состояние */
        });
    },
    [platform, load]
  );

  const handleCloseModal = () => {
    // Закрыли модалку — отслеживание загрузки больше не нужно
    trackAbortRef.current?.abort();
    trackAbortRef.current = null;
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
        trackRefresh(result.task_id);
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
            <Button
              variant="outline"
              onClick={onOpenMonitor}
              title="Очередь и прогресс всех загрузок спеков"
            >
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
            {visibleNames.map((cat, idx) => (
              <CategoryCard
                key={cat.category_id || cat.category_name || idx}
                cat={cat}
                isAdmin={isAdmin}
                isDeleting={deletingKey === (cat.category_id || cat.category_name)}
                onOpenDetail={openSpecDetail}
                onDelete={handleDeleteOne}
              />
            ))}

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

export default SpecsPage;
