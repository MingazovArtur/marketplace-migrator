import React, { useState, useEffect, useCallback, useRef } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { api } from '../../api';

const POLL_INTERVAL_MS = 700;

/**
 * Модалка миграции одной карточки товара на выбранную площадку.
 *
 * ✅ v3:
 *  - Блокирует кнопку «Мигрировать» при цене ≤ 0 с явным красным алертом.
 *  - Показывает выпадающий список категорий из спеков площадки.
 *  - Polling прогресса Celery-задачи.
 *  - Галочка «Автоматически скачать XLSX после миграции».
 *  - Авто-экспорт скачивает ТОЛЬКО ОДИН мигрированный товар (передаём product.id),
 *    а не все успешные (которые скачиваются через «Выгрузка для площадки»).
 *  - Корректно вызывает refreshAll через onSaved.
 */
const MigrateModal = ({
  isOpen,
  onClose,
  product,              // «живой» объект товара (getProductById из App)
  onConfirm,            // (productId, platform, editedData, autoExport) => Promise
  loading = false,
  onSaved,              // ← refreshAll из App.jsx (обновляет список + refreshKey)
  onNotify,             // опциональный setMessage из App
}) => {
  const [platform, setPlatform] = useState('ozon');
  const [form, setForm] = useState({ name: '', price: '', category: '' });
  const [specCategories, setSpecCategories] = useState([]);
  const [specsLoading, setSpecsLoading] = useState(false);
  const [autoExport, setAutoExport] = useState(true);
  const [progress, setProgress] = useState(null);
  const [localError, setLocalError] = useState('');
  const pollTimerRef = useRef(null);

  // Загрузка списка категорий спеков для выбранной площадки
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

  // Инициализация формы при открытии / смене товара
  useEffect(() => {
    if (isOpen && product) {
      setForm({
        name: product.name || '',
        price: product.price != null ? String(product.price) : '',
        category: product.mapped_category || '',
      });
      setLocalError('');
      setProgress(null);
      loadSpecCategories(platform);
    }
  }, [isOpen, product, platform, loadSpecCategories]);

  // Очистка polling при размонтировании
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  if (!isOpen || !product) return null;

  // ✅ Валидация цены: блокируем миграцию при 0 или невалидном значении
  const priceNum = Number(form.price);
  const priceInvalid = !Number.isFinite(priceNum) || priceNum <= 0;

  // Polling прогресса Celery-задачи
  const pollProgress = useCallback(async (taskId) => {
    try {
      const data = await api.getTaskProgress(taskId);
      setProgress(data);
      if (data.status === 'completed' || data.status === 'failed') {
        if (pollTimerRef.current) {
          clearTimeout(pollTimerRef.current);
          pollTimerRef.current = null;
        }

        // Вызов refreshAll, чтобы обновить список товаров и refreshKey
        if (onSaved && data.status === 'completed') {
          try {
            await onSaved();
          } catch (e) {
            console.warn('refreshAll failed:', e);
          }
        }

        // ✅ Авто-скачивание XLSX после успешной миграции — ТОЛЬКО ОДИН ТОВАР
        if (data.status === 'completed' && autoExport && platform === 'ozon' && product?.id) {
          try {
            await api.exportXlsxV2('ozon', 'success', product.id);
            if (onNotify) {
              onNotify(
                `✅ Карточка #${product.id} перенесена. ` +
                `XLSX с этим товаром скачан — загрузите его в кабинете Ozon.`
              );
            }
          } catch (e) {
            if (onNotify) {
              onNotify(
                `✅ Карточка #${product.id} перенесена, но XLSX не скачался: ${e.message}`
              );
            }
          }
        }

        if (data.status === 'completed') {
          setTimeout(onClose, 600);
        }
      } else {
        pollTimerRef.current = setTimeout(() => pollProgress(taskId), POLL_INTERVAL_MS);
      }
    } catch (e) {
      setLocalError(`Не удалось получить прогресс: ${e.message}`);
    }
  }, [autoExport, platform, onClose, onSaved, onNotify, product]);

  const handleSubmit = async () => {
    if (priceInvalid) {
      setLocalError('Цена должна быть больше 0 ₽ — Ozon отклонит карточку с нулевой ценой.');
      return;
    }

    setLocalError('');
    setProgress({ status: 'pending', percent: 0 });

    const editedData = {
      name: form.name.trim() || product.name,
      price: priceNum,
      category: form.category || undefined,
    };

    try {
      const result = await api.migrateProduct(product.id, platform, editedData);
      if (result && result.task_id) {
        pollProgress(result.task_id);
      } else {
        // Синхронный ответ без task_id — вызываем onConfirm напрямую
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
  };

  const percent = progress?.percent ?? 0;
  const isInProgress = progress && (progress.status === 'progress' || progress.status === 'pending');
  const isCompleted = progress?.status === 'completed';
  const isFailed = progress?.status === 'failed';

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

        <div style={{ marginBottom: '0.75rem', padding: '0.5rem 0.75rem', background: 'var(--bg-secondary)', borderRadius: 6, fontSize: '0.85rem' }}>
          <div style={{ color: 'var(--text-muted)' }}>Товар:</div>
          <div style={{ fontWeight: 600 }}>{product.name}</div>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            ID {product.id} · {product.source || 'без источника'}
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
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        {/* Название */}
        <label className="form-label" style={{ marginTop: '0.6rem' }}>Название товара</label>
        <input
          className="form-input"
          type="text"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          placeholder={product.name}
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
          onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
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
              ❌ Цена должна быть больше 0 ₽ — без цены Ozon отклонит карточку,
              и товар не попадёт в выгрузку. Укажите цену в поле выше.
            </div>
          </div>
        )}

        {/* Категория */}
        <label className="form-label" style={{ marginTop: '0.6rem' }}>
          Категория на {PLATFORMS.find((p) => p.id === platform)?.name || 'площадке'}
        </label>
        <input
          className="form-input"
          type="text"
          list={`spec-categories-${platform}`}
          value={form.category}
          onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
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
            : `Формат «Родитель / Тип». Список из ${specCategories.length} категорий — из спека ${platform}.`}
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
          Будет скачан XLSX <strong>только с этим товаром</strong>.
          Для массовой выгрузки всех товаров используйте «Выгрузка для площадки».
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