import React, { useState, useEffect, useCallback, useRef } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { api } from '../../api';

const MigrateModal = ({
  isOpen,
  onClose,
  product,
  onConfirm,
  loading = false,
  onSaved,
  onNotify,
}) => {
  const [platform, setPlatform] = useState('ozon');
  const [form, setForm] = useState({ name: '', price: '', category: '' });
  const [specCategories, setSpecCategories] = useState([]);
  const [specsLoading, setSpecsLoading] = useState(false);
  const [autoExport, setAutoExport] = useState(true);
  const [progress, setProgress] = useState(null);
  const [localError, setLocalError] = useState('');
  const [saveState, setSaveState] = useState('idle'); // idle | saving | saved
  // ✅ Свежая копия товара из БД: App-список мог устареть (например, после
  // «Заполнить пропуски» дефолтной ценой) — модалка обязана показывать
  // и отправлять на миграцию актуальную цену, а не «0» из старого кэша.
  const [fetched, setFetched] = useState(null);
  const touchedRef = useRef(false); // пользователь уже правил поля — не затираем его ввод
  const trackAbortRef = useRef(null); // отмена SSE-потока прогресса (Round 8)

  // Свежие данные: из БД, как только пришли; до тех пор — из пропса.
  // Объявлены ДО useCallback'ов: productTitle попадает в их deps.
  const baseProduct = fetched || product;
  const productTitle = baseProduct?.name || '';

  const loadSpecCategories = useCallback(async (pl) => {
    setSpecsLoading(true);
    try {
      const names = await api.getSpecNames(pl);
      setSpecCategories(Array.isArray(names) ? names : []);
    } catch (e) {
      setSpecCategories([]);
    } finally {
      setSpecsLoading(false);
    }
  }, []);

  // ✅ Round 8: прогресс — SSE-поток (кадры пушем), polling — резерв в api/sse.js.
  // Каждый кадр обновляет прогресс-бар; терминальный завершает ожидание.
  const trackProgress = useCallback(
    async (taskId) => {
      trackAbortRef.current?.abort();
      const ac = new AbortController();
      trackAbortRef.current = ac;
      try {
        const data = await api.streamTaskProgress(taskId, {
          onUpdate: setProgress,
          onError: (e) => setLocalError(`Связь с сервером: ${e.message} (продолжаем пробовать)`),
          timeoutMs: 15 * 60 * 1000,
          timeoutMessage: 'Таймаут ожидания миграции (15 мин). Проверьте логи Celery.',
          signal: ac.signal,
        });
        setProgress(data);

        if (data.status !== 'completed') {
          return; // failed: прогресс-бар уже показывает ошибку (data.error)
        }

        if (onSaved) {
          try {
            await onSaved();
          } catch (e) {
            console.warn('refreshAll failed:', e);
          }
        }

        // ✅ ИСПРАВЛЕНО: автоскачивание ТОЛЬКО этого товара (product.id) работает для всех площадок
        if (autoExport && product?.id) {
          const platformTitle = PLATFORMS.find((p) => p.id === platform)?.name || platform;
          try {
            await api.exportXlsxV2(platform, 'success', product.id);
            if (onNotify) {
              onNotify(
                `✅ Карточка #${product.id} перенесена. ` +
                  `XLSX только с этим товаром скачан — загрузите его в кабинете ${platformTitle}.`
              );
            }
          } catch (e) {
            if (onNotify) {
              onNotify(`✅ Карточка #${product.id} перенесена, но XLSX не скачался: ${e.message}`);
            }
          }
        }

        setTimeout(onClose, 600);
      } catch (e) {
        if (!ac.signal.aborted) {
          setLocalError(`Не удалось получить прогресс: ${e.message}`);
        }
      } finally {
        if (trackAbortRef.current === ac) trackAbortRef.current = null;
      }
    },
    [autoExport, platform, onClose, onSaved, onNotify, product]
  );

  const handleSubmit = useCallback(async () => {
    const priceNum = Number(form.price);
    const priceInvalid = !Number.isFinite(priceNum) || priceNum <= 0;

    if (priceInvalid) {
      setLocalError('Цена должна быть больше 0 ₽ — площадка отклонит карточку с нулевой ценой.');
      return;
    }

    setLocalError('');
    setProgress({ status: 'pending', percent: 0 });

    const editedData = {
      name: form.name.trim() || productTitle,
      price: priceNum,
      category: form.category || undefined,
    };

    try {
      const result = await api.migrateProduct(product.id, platform, editedData);
      if (result && result.task_id) {
        trackProgress(result.task_id);
      } else {
        if (onConfirm) {
          await onConfirm(product.id, platform, editedData, autoExport);
        }
        if (onSaved) await onSaved();
        setTimeout(onClose, 300);
      }
    } catch (e) {
      setLocalError(e.message);
      setProgress(null);
    }
  }, [form, product, platform, autoExport, onConfirm, onSaved, onClose, trackProgress, productTitle]);

  // Сохранить изменения (название/цена/категория) в товаре БЕЗ запуска миграции —
  // товары из файлов часто приходят с ценой 0, раньше её было негде сохранить,
  // не запуская миграцию
  const handleSave = useCallback(async () => {
    const priceNum = Number(form.price);
    if (!Number.isFinite(priceNum) || priceNum <= 0) {
      setLocalError('Чтобы сохранить, укажите цену больше 0 ₽.');
      return;
    }
    const name = form.name.trim() || productTitle;
    if (!name) {
      setLocalError('Укажите название товара.');
      return;
    }

    setLocalError('');
    setSaveState('saving');
    try {
      const r = await api.updateProduct(product.id, {
        name,
        price: priceNum,
        category: form.category || null,
      });
      setSaveState('saved');
      // ✅ Синхронизируем локальную копию с ответом PATCH — цена/имя/категория
      // в модалке совпадают с тем, что реально лежит в БД
      if (r && r.product) {
        setFetched((prev) => ({ ...(prev || product), ...r.product }));
      }
      if (onNotify) {
        onNotify(
          `✅ Товар #${product.id}: изменения сохранены (цена ${priceNum} ₽). Можно мигрировать.`
        );
      }
      if (onSaved) {
        try {
          await onSaved();
        } catch (e) {
          console.warn('refreshAll failed:', e);
        }
      }
      setTimeout(() => setSaveState('idle'), 4000);
    } catch (e) {
      setSaveState('idle');
      setLocalError(`Не удалось сохранить: ${e.message}`);
    }
  }, [form, product, onSaved, onNotify, productTitle]);

  useEffect(() => {
    // ✅ При открытии подтягиваем товар из БД — защита от устаревшего кэша списка
    if (!isOpen || !product?.id) return undefined;
    setFetched(null);
    touchedRef.current = false;
    let cancelled = false;
    api
      .getProduct(product.id)
      .then((fresh) => {
        if (!cancelled && !touchedRef.current && fresh && fresh.id) {
          setFetched(fresh);
        }
      })
      .catch(() => {/* сеть недоступна — остаёмся на данных пропса */});
    return () => {
      cancelled = true;
    };
  }, [isOpen, product?.id]);

  useEffect(() => {
    if (isOpen && product && !touchedRef.current) {
      setForm({
        name: baseProduct.name || '',
        price: baseProduct.price != null ? String(baseProduct.price) : '',
        category: baseProduct.mapped_category || '',
      });
      setLocalError('');
      setProgress(null);
    }
    // platform НЕ в зависимостях: смена площадки не должна сбрасывать
    // уже введённые название/цену (раньше форма очищалась)
  }, [isOpen, product, fetched]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (isOpen) loadSpecCategories(platform);
  }, [isOpen, platform, loadSpecCategories]);

  // ✅ Round 8: отмена SSE-потока прогресса при размонтировании
  useEffect(() => {
    return () => {
      trackAbortRef.current?.abort();
    };
  }, []);

  if (!isOpen || !product) return null;

  const priceNum = Number(form.price);
  const priceInvalid = !Number.isFinite(priceNum) || priceNum <= 0;
  const percent = progress?.percent ?? 0;
  const isInProgress =
    progress && (progress.status === 'progress' || progress.status === 'pending');
  const isCompleted = progress?.status === 'completed';
  const isFailed = progress?.status === 'failed';
  const platformTitle = PLATFORMS.find((p) => p.id === platform)?.name || 'площадке';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="migrate" size={22} /> Миграция карточки
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <div
          style={{
            marginBottom: '0.75rem',
            padding: '0.5rem 0.75rem',
            background: 'var(--bg-secondary)',
            borderRadius: 6,
            fontSize: '0.85rem',
          }}
        >
          <div style={{ color: 'var(--text-muted)' }}>Товар:</div>
          <div style={{ fontWeight: 600 }}>{productTitle}</div>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            ID {product.id} · {baseProduct.source || product.source || 'без источника'}
          </div>
        </div>

        {/* Площадка */}
        <label className="form-label">Площадка назначения</label>
        <select
          className="form-input"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          disabled={isInProgress}
        >
          {PLATFORMS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>

        {/* Название */}
        <label className="form-label" style={{ marginTop: '0.6rem' }}>
          Название товара
        </label>
        <input
          className="form-input"
          type="text"
          value={form.name}
          onChange={(e) => {
            touchedRef.current = true;
            setForm((f) => ({ ...f, name: e.target.value }));
          }}
          placeholder={productTitle}
          disabled={isInProgress}
        />

        {/* Цена */}
        <label className="form-label" style={{ marginTop: '0.6rem' }}>
          Цена, ₽ <span style={{ color: 'var(--danger, #ef4444)' }}>*</span>
        </label>
        <input
          className="form-input"
          type="number"
          step="0.01"
          min="0.01"
          value={form.price}
          onChange={(e) => {
            touchedRef.current = true;
            setForm((f) => ({ ...f, price: e.target.value }));
          }}
          placeholder="990"
          disabled={isInProgress}
          style={priceInvalid && form.price ? { borderColor: 'var(--danger, #ef4444)' } : {}}
        />
        {priceInvalid && (
          <div
            className="alert alert-error"
            style={{ marginTop: '0.4rem', padding: '0.5rem 0.75rem', fontSize: '0.85rem' }}
          >
            <div>
              ❌ Цена должна быть больше 0 ₽ — без цены площадка отклонит карточку, и товар не попадёт в
              выгрузку. Укажите цену в поле выше.
            </div>
          </div>
        )}

        {/* Категория */}
        <label className="form-label" style={{ marginTop: '0.6rem' }}>
          Категория на {platformTitle}
        </label>
        <input
          className="form-input"
          type="text"
          list={`spec-categories-${platform}`}
          value={form.category}
          onChange={(e) => {
            touchedRef.current = true;
            setForm((f) => ({ ...f, category: e.target.value }));
          }}
          placeholder="Одежда / Футболка"
          disabled={isInProgress || specsLoading}
        />
        <datalist id={`spec-categories-${platform}`}>
          {specCategories.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <p className="form-hint">
          {specsLoading
            ? 'Загружаем список категорий спека...'
            : specCategories.length > 0
              ? `Формат «Родитель / Тип». Список из ${specCategories.length} категорий — из спека ${platformTitle}.`
              : `Укажите название категории на ${platformTitle} (или оставьте для автоподбора).`}
        </p>

        {/* Авто-экспорт */}
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            marginTop: '0.75rem',
            cursor: 'pointer',
            fontSize: '0.9rem',
          }}
        >
          <input
            type="checkbox"
            checked={autoExport}
            onChange={(e) => setAutoExport(e.target.checked)}
            disabled={isInProgress}
          />
          <span>Автоматически скачать XLSX для этого товара</span>
        </label>
        <p className="form-hint">
          Будет скачан XLSX <strong>только с этим товаром (#{product.id})</strong>. Для массовой
          выгрузки используйте кнопку «Выгрузка для площадки».
        </p>

        {/* Прогресс */}
        {isInProgress && (
          <div style={{ marginTop: '0.75rem' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '0.85rem',
                marginBottom: '0.25rem',
                color: 'var(--text-secondary)',
              }}
            >
              <span>Миграция...</span>
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
                  background: 'var(--primary, #3b82f6)',
                  transition: 'width 0.3s',
                }}
              />
            </div>
          </div>
        )}

        {isCompleted && (
          <div className="alert alert-success" style={{ marginTop: '0.75rem' }}>
            <div>
              ✅ Карточка #{product.id} успешно мигрирована
              {autoExport ? '. XLSX с этим товаром скачивается...' : ''}
            </div>
          </div>
        )}

        {isFailed && (
          <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
            <div>❌ Ошибка миграции: {progress?.error || 'неизвестная ошибка'}</div>
          </div>
        )}

        {localError && !isInProgress && (
          <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
            <div>{localError}</div>
          </div>
        )}

        {/* Действия */}
        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={isInProgress}>
            {isCompleted || isFailed ? 'Закрыть' : 'Отмена'}
          </Button>
          <Button
            variant="outline"
            onClick={handleSave}
            disabled={isInProgress || isCompleted || saveState !== 'idle'}
            loading={saveState === 'saving'}
            title="Сохранить название, цену и категорию в товаре без запуска миграции"
          >
            <Icon name="save" size={16} /> {saveState === 'saved' ? 'Сохранено' : 'Сохранить'}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={loading || isInProgress || priceInvalid || isCompleted}
            loading={loading && !progress}
          >
            <Icon name="migrate" size={16} /> Мигрировать
          </Button>
        </div>
      </div>
    </div>
  );
};

export default MigrateModal;