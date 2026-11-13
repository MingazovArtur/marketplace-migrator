import React, { useEffect, useMemo, useState } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api } from '../../api';

/**
 * Массовое обновление выбранных товаров: цена (наценка/скидка %), бренд,
 * категория назначения.
 *
 * UX-спринт:
 *  - живой предпросмотр: цены «до → после» по реальным товарам (POST /products/bulk-preview);
 *  - автокомплит категории из спеков площадок + индикация «нет в спеках»;
 *  - защита: наценка ≤ −100% блокируется инлайн (без alert());
 *  - защита от повторной наценки: те же товары + тот же % в течение 15 минут —
 *    предупреждение и кнопка «Всё равно применить»;
 *  - onSubmit возвращает true/false; после успеха ProductsPage показывает
 *    кнопку «Отменить» (undo-снапшот на бэкенде).
 */

// Окно, в котором повторная наценка тех же товаров считается подозрительной
const REAPPLY_WINDOW_MS = 15 * 60 * 1000;
const REAPPLY_LOG_KEY = 'bulk_percent_applied_at';

const fmt = (v) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : `${Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽`;

const readReapplyLog = () => {
  try {
    const raw = JSON.parse(localStorage.getItem(REAPPLY_LOG_KEY) || 'null');
    return raw && typeof raw.ts === 'number' ? raw : null;
  } catch (e) {
    return null;
  }
};

const BulkUpdateModal = ({ selectedIds = [], count, loading, onSubmit, onClose }) => {
  const [pricePercent, setPricePercent] = useState('');
  const [brand, setBrand] = useState('');
  const [category, setCategory] = useState('');

  const [preview, setPreview] = useState(null); // ответ /bulk-preview
  const [previewLoading, setPreviewLoading] = useState(false);
  const [confirmReapply, setConfirmReapply] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const percentValue = useMemo(() => {
    const v = parseFloat(String(pricePercent).replace(',', '.'));
    return Number.isFinite(v) ? v : null;
  }, [pricePercent]);

  const hasPercent = pricePercent.trim() !== '' && percentValue !== null;
  const hasBrand = brand.trim() !== '';
  const hasCategory = category.trim() !== '';
  const canSubmit = (hasPercent || hasBrand || hasCategory) && !submitting && !loading;

  /* ---------- Валидация (инлайн, без alert) ---------- */
  const percentError =
    hasPercent && percentValue <= -100
      ? 'Наценка ≤ −100% обнулит цены — нельзя'
      : hasPercent && percentValue === 0
        ? '0% не изменит цены'
        : null;

  /* ---------- Повторная наценка тех же товаров ---------- */
  const reapplyWarning = useMemo(() => {
    if (!hasPercent) return null;
    const log = readReapplyLog();
    if (!log || log.percent !== percentValue) return null;
    const sameSelection =
      JSON.stringify([...(log.ids || [])].sort()) === JSON.stringify([...selectedIds].sort());
    if (!sameSelection || Date.now() - log.ts >= REAPPLY_WINDOW_MS) return null;
    const mins = Math.max(1, Math.round((Date.now() - log.ts) / 60000));
    return `Вы уже применяли ${percentValue > 0 ? '+' : ''}${percentValue}% к этим же товарам ${mins} мин назад. Повторное применение посчитает процент уже от изменённой цены.`;
  }, [hasPercent, percentValue, selectedIds]);

  /* ---------- Живой предпросмотр (debounce 350 мс) ---------- */
  useEffect(() => {
    if (!canSubmit || percentError || !selectedIds.length) {
      setPreview(null);
      return undefined;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const r = await api.bulkPreviewProducts({
          product_ids: selectedIds,
          price_percent: hasPercent ? percentValue : undefined,
          brand: hasBrand ? brand.trim() : undefined,
          category: hasCategory ? category.trim() : undefined,
        });
        if (!cancelled) setPreview(r);
      } catch (e) {
        if (!cancelled) setPreview(null);
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [
    canSubmit,
    percentError,
    selectedIds,
    hasPercent,
    percentValue,
    hasBrand,
    brand,
    hasCategory,
    category,
  ]);

  const submit = async (force = false) => {
    if (!canSubmit) return;
    if (reapplyWarning && !force) {
      setConfirmReapply(true); // первый клик — показать предупреждение
      return;
    }
    setSubmitting(true);
    const payload = {
      price_percent: hasPercent ? percentValue : undefined,
      brand: hasBrand ? brand.trim() : undefined,
      category: hasCategory ? category.trim() : undefined,
    };
    const ok = await onSubmit(payload);
    setSubmitting(false);
    if (ok && hasPercent) {
      try {
        localStorage.setItem(
          REAPPLY_LOG_KEY,
          JSON.stringify({ percent: percentValue, ids: selectedIds, ts: Date.now() })
        );
      } catch (e) {
        /* приватный режим — без защиты от повторов */
      }
    }
  };

  const previewData = preview?.preview;
  const categoryInfo = preview?.category;

  return (
    <div className="modal-overlay" onClick={loading || submitting ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="edit" size={20} /> Массовое обновление ({count})
          </h2>
          <button
            type="button"
            className="close-btn"
            onClick={onClose}
            disabled={loading || submitting}
            title="Закрыть"
          >
            <Icon name="close" size={16} />
          </button>
        </div>

        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Заполните только то, что нужно изменить. После применения появится кнопка «Отменить».
        </p>

        {/* ---------- Цена ---------- */}
        <label className="form-label">Наценка / скидка, %</label>
        <input
          className={`form-input ${percentError ? 'input-error' : ''}`}
          type="number"
          value={pricePercent}
          onChange={(e) => {
            setPricePercent(e.target.value);
            setConfirmReapply(false);
          }}
          placeholder="Например: 15 или -10"
          disabled={loading || submitting}
        />
        {percentError ? (
          <p className="form-hint" style={{ color: 'var(--danger, #ef4444)' }}>
            {percentError}
          </p>
        ) : (
          <p className="form-hint">Цена каждого товара будет умножена на (1 + %/100).</p>
        )}

        {/* ---------- Бренд ---------- */}
        <label className="form-label">Бренд</label>
        <input
          className="form-input"
          type="text"
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
          placeholder="Оставьте пустым, чтобы не менять"
          disabled={loading || submitting}
        />

        {/* ---------- Категория с автокомплитом ---------- */}
        <CategoryInput
          value={category}
          onChange={(v) => setCategory(v)}
          disabled={loading || submitting}
          validity={categoryInfo}
        />

        {/* ---------- Предпросмотр ---------- */}
        {canSubmit && !percentError && selectedIds.length > 0 && (
          <PreviewBox
            loading={previewLoading}
            preview={previewData}
            categoryInfo={categoryInfo}
            hasBrand={hasBrand}
            brand={brand.trim()}
          />
        )}

        {/* ---------- Подтверждение повторной наценки ---------- */}
        {reapplyWarning && confirmReapply && (
          <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
            <div>
              <strong>⚠ Повторная наценка.</strong> {reapplyWarning}
            </div>
          </div>
        )}

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={loading || submitting}>
            Отмена
          </Button>
          {reapplyWarning && confirmReapply ? (
            <Button onClick={() => submit(true)} disabled={loading} loading={submitting}>
              Всё равно применить
            </Button>
          ) : (
            <Button
              onClick={() => submit()}
              disabled={!canSubmit || !!percentError}
              loading={submitting || loading}
            >
              <Icon name="edit" size={16} /> Применить
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

/* ==================== Категория: input + datalist + статус ==================== */

const CategoryInput = ({ value, onChange, disabled, validity }) => {
  const [suggestions, setSuggestions] = useState([]);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const r = await api.categorySuggestions(value.trim(), 15);
        if (!cancelled) setSuggestions(r.suggestions || []);
      } catch (e) {
        if (!cancelled) setSuggestions([]);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [value]);

  const matched = value.trim() ? suggestions.find((s) => s.name === value.trim()) : null;
  const known = validity ? validity.valid : matched ? true : null; // null = ещё не проверено
  const platforms = validity?.platforms?.length
    ? validity.platforms
    : matched
      ? matched.platforms
      : [];

  return (
    <>
      <label className="form-label">Категория назначения</label>
      <input
        className="form-input"
        type="text"
        list="bulk-category-suggestions"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Начните вводить — подскажем из спеков площадок"
        disabled={disabled}
      />
      <datalist id="bulk-category-suggestions">
        {suggestions.map((s) => (
          <option key={s.name} value={s.name}>
            {s.platforms.join(', ')}
          </option>
        ))}
      </datalist>
      {value.trim() === '' ? (
        <p className="form-hint">Оставьте пустым, чтобы не менять.</p>
      ) : known === false ? (
        <p className="form-hint" style={{ color: 'var(--accent-warning, #f59e0b)' }}>
          ⚠ Не найдена в спеках площадок — миграция завершится ошибкой. Выберите вариант из
          подсказок.
        </p>
      ) : known === true ? (
        <p className="form-hint" style={{ color: 'var(--accent-success, #22c55e)' }}>
          ✓ Есть в спеках{platforms.length ? `: ${platforms.join(', ')}` : ''}
        </p>
      ) : (
        <p className="form-hint">Например: Одежда / Футболка. Значения из спеков подсвечиваются.</p>
      )}
    </>
  );
};

/* ==================== Блок предпросмотра ==================== */

const PreviewBox = ({ loading, preview, categoryInfo, hasBrand, brand }) => {
  if (loading) {
    return (
      <div className="bulk-preview" style={{ opacity: 0.6 }}>
        <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Считаем
        предпросмотр…
      </div>
    );
  }
  if (!preview) return null;

  const {
    count,
    prices_changed: pc,
    price_min: min,
    price_max: max,
    price_avg: avg,
    sample,
    invalid_prices: invalid,
  } = preview || {};

  return (
    <div className="bulk-preview">
      <div className="bulk-preview-title">
        <Icon name="info" size={15} /> Предпросмотр · {count} тов.
      </div>
      {pc && min !== null && max !== null && min !== max && (
        <div className="bulk-preview-row">
          Новые цены: от <b>{fmt(min)}</b> до <b>{fmt(max)}</b>
          {avg !== null && <> (в среднем {fmt(avg)})</>}
        </div>
      )}
      {pc && min !== null && min === max && (
        <div className="bulk-preview-row">
          Новая цена: <b>{fmt(min)}</b>
        </div>
      )}
      {pc && min === null && (
        <div className="bulk-preview-row bulk-preview-warn">
          Цена не пересчитается — у выделенных товаров она не задана
        </div>
      )}
      {pc && invalid > 0 && (
        <div className="bulk-preview-row bulk-preview-warn">
          ⚠ У {invalid} товаров цена ≤ 0 — процент на них не пересчитается
        </div>
      )}
      {sample && sample.length > 0 && pc && (
        <div className="bulk-preview-sample">
          {sample.map((s) => (
            <div key={s.id} className="bulk-preview-row" title={s.name}>
              · {s.name.length > 32 ? `${s.name.slice(0, 32)}…` : s.name}: <b>{fmt(s.old_price)}</b>{' '}
              → <b>{fmt(s.new_price)}</b>
            </div>
          ))}
        </div>
      )}
      {hasBrand && (
        <div className="bulk-preview-row">
          Бренд всем: <b>{brand || '— (очистить)'}</b>
        </div>
      )}
      {categoryInfo && categoryInfo.valid === false && (
        <div className="bulk-preview-row bulk-preview-warn">
          ⚠ Категория не найдена в спеках площадок
        </div>
      )}
    </div>
  );
};

export default BulkUpdateModal;
