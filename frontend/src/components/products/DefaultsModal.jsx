import React, { useState, useEffect, useCallback } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api } from '../../api';

const VAT_OPTIONS = [
  { value: 'none', label: 'Не облагается' },
  { value: '20', label: '20' },
  { value: '10', label: '10' },
  { value: '7', label: '7' },
  { value: '5', label: '5' },
];

const EMPTY_FORM = {
  vat_rate: '',
  okpd_code: '',
  package_weight_grams: '',
  package_width_mm: '',
  package_height_mm: '',
  package_length_mm: '',
  brand: '',
  marking: 'Нет',
  price_default: '', // ✅ цена по умолчанию для дозаполнения нулевых
};

const GAP_LABELS = {
  vat_rate: 'НДС, %',
  okpd_code: 'ТН ВЭД коды ЕАЭС',
  package_weight_grams: 'Вес в упаковке, г',
  package_width_mm: 'Ширина упаковки, мм',
  package_height_mm: 'Высота упаковки, мм',
  package_length_mm: 'Длина упаковки, мм',
  price: 'Цена > 0',
  main_photo: 'Главное фото',
};

/**
 * Модалка «Дефолты экспорта»: глобальные значения + значения по категориям.
 * Позволяет настроить заполнение пропусков ОДИН раз для тысяч товаров.
 */
const DefaultsModal = ({ isOpen, onClose, onNotify, specNames = [], productCategories = [] }) => {
  const [tab, setTab] = useState('global'); // global | category
  const [category, setCategory] = useState('');
  const [form, setForm] = useState(EMPTY_FORM);
  const [saved, setSaved] = useState({ global: null, categories: [] });
  const [gaps, setGaps] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const load = useCallback(async () => {
    const [d, g] = await Promise.all([api.getDefaults(), api.getGaps('all')]);
    setSaved(d);
    setGaps(g);
    return d;
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    load().then((d) => {
      setForm({ ...EMPTY_FORM, ...(d.global || {}) });
    });
  }, [isOpen, load]);

  useEffect(() => {
    if (!isOpen) return;
    const found = (saved.categories || []).find((c) => c.category_name === category);
    setForm({ ...EMPTY_FORM, ...(found || saved.global || {}), category_name: category });
  }, [category, isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isOpen) return null;

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  // Что сейчас на экране → payload для PUT /defaults (одна схема для
  // «Сохранить дефолты» и для «Заполнить пропуски»)
  const buildPayload = () => ({
    category_name: tab === 'category' ? category || null : null,
    vat_rate: form.vat_rate || null,
    okpd_code: form.okpd_code || null,
    package_weight_grams: form.package_weight_grams ? Number(form.package_weight_grams) : null,
    package_width_mm: form.package_width_mm ? Number(form.package_width_mm) : null,
    package_height_mm: form.package_height_mm ? Number(form.package_height_mm) : null,
    package_length_mm: form.package_length_mm ? Number(form.package_length_mm) : null,
    brand: form.brand || null,
    marking: form.marking || null,
    price_default: form.price_default ? Number(form.price_default) : null, // цена по умолчанию
  });

  const handleSave = async () => {
    setLoading(true);
    try {
      await api.saveDefaults(buildPayload());
      await load();
      if (onNotify) onNotify('✅ Дефолты сохранены');
    } catch (e) {
      if (onNotify) onNotify(`❌ ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  // ✅ «Заполнить пропуски» сначала сохраняет то, что сейчас на экране, и только
  // потом применяет. Раньше кнопка применяла СТАРЫЕ сохранённые дефолты: пользователь
  // вводил цену 99.97, жал «Заполнить» — и ничего не заполнялось, потому что
  // он не нажал «Сохранить дефолты» отдельно.
  const handleApply = async () => {
    setApplying(true);
    try {
      await api.saveDefaults(buildPayload());
      const r = await api.applyDefaults('all');
      if (onNotify) {
        onNotify(
          `🩹 Дефолты сохранены. Заполнено товаров: ${r.updated} из ${r.total}` +
            (Object.keys(r.fields || {}).length
              ? ` (поля: ${Object.entries(r.fields)
                  .map(([k, v]) => `${GAP_LABELS[k] || k}: ${v}`)
                  .join(', ')})`
              : '')
        );
      }
      await load();
    } catch (e) {
      if (onNotify) onNotify(`❌ ${e.message}`);
    } finally {
      setApplying(false);
    }
  };

  const gapEntries = gaps ? Object.entries(gaps.gaps || {}).filter(([, n]) => n > 0) : [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="settings" size={22} /> Дефолты экспорта и авто-заполнение
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        {/* Баннер пропусков + кнопка массового заполнения */}
        {gaps && gaps.total > 0 && (
          <div
            className={gapEntries.length ? 'alert alert-error' : 'alert alert-success'}
            style={{ marginBottom: '0.75rem', alignItems: 'flex-start' }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              {gapEntries.length ? (
                <>
                  Не хватает полей у <strong>{gaps.products_with_gaps ?? gaps.total}</strong> из{' '}
                  {gaps.total} товаров:{' '}
                  {gapEntries.map(([k, n]) => `${GAP_LABELS[k] || k} — ${n}`).join('; ')}.
                  <div style={{ marginTop: '0.3rem', fontSize: '0.8rem', opacity: 0.8 }}>
                    Заполните значения ниже и нажмите кнопку — она сама сохранит их и применит.
                  </div>
                  <div style={{ marginTop: '0.5rem' }}>
                    <Button size="small" onClick={handleApply} loading={applying}>
                      🩹 Заполнить пропуски (все товары)
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  ✅ Пропусков обязательных полей нет — все {gaps.total} товаров готовы к выгрузке.
                </>
              )}
            </div>
          </div>
        )}

        {/* Вкладки */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <Button
            variant={tab === 'global' ? 'primary' : 'outline'}
            size="small"
            onClick={() => setTab('global')}
          >
            Глобальные дефолты
          </Button>
          <Button
            variant={tab === 'category' ? 'primary' : 'outline'}
            size="small"
            onClick={() => setTab('category')}
          >
            Дефолты категории
          </Button>
        </div>

        {tab === 'category' && (
          <div style={{ marginBottom: '0.75rem' }}>
            <label className="form-label">Категория (mapped_category)</label>
            <input
              className="form-input"
              list="defaults-categories"
              placeholder="Одежда / Футболка"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
            <datalist id="defaults-categories">
              {Array.from(new Set([...productCategories, ...specNames])).map((n) => (
                <option key={n} value={n} />
              ))}
            </datalist>
            <p className="form-hint">
              Значения категории перекрывают глобальные. Настройте ТН ВЭД/ОВХ один раз — они
              применятся ко всем товарам категории при «Заполнить пропуски» и при миграции.
            </p>
            {(saved.categories || []).length > 0 && (
              <div
                style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.4rem' }}
              >
                Настроены категории:{' '}
                {(saved.categories || []).map((c) => (
                  <span
                    key={c.category_name}
                    style={{ marginRight: '0.6rem', whiteSpace: 'nowrap' }}
                  >
                    ✅ {c.category_name}{' '}
                    <button
                      type="button"
                      title="Удалить дефолты категории"
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--danger, #ef4444)',
                        cursor: 'pointer',
                        padding: 0,
                      }}
                      onClick={async () => {
                        await api.deleteCategoryDefaults(c.category_name);
                        await load();
                      }}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Форма дефолтов */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem 1rem' }}>
          <div>
            <label className="form-label">Цена по умолчанию, ₽</label>
            <input
              className="form-input"
              type="number"
              min="0.01"
              step="0.01"
              value={form.price_default ?? ''}
              onChange={set('price_default')}
              placeholder="Например: 990"
            />
            <p
              className="form-hint"
              style={{ color: 'var(--warning, #f59e0b)', fontSize: '0.8rem', marginTop: '0.25rem' }}
            >
              ⚠ Подставится только товарам с ценой 0/пустой. Существующие цены не трогаем — Ozon
              продаёт ровно по цене в файле.
            </p>
          </div>
          <div>
            <label className="form-label">НДС, %</label>
            <select className="form-input" value={form.vat_rate || ''} onChange={set('vat_rate')}>
              <option value="">— не задан —</option>
              {VAT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">ТН ВЭД коды ЕАЭС</label>
            <input
              className="form-input"
              value={form.okpd_code || ''}
              onChange={set('okpd_code')}
              placeholder="6109100010"
            />
          </div>
          <div>
            <label className="form-label">Вес в упаковке, г</label>
            <input
              className="form-input"
              type="number"
              value={form.package_weight_grams ?? ''}
              onChange={set('package_weight_grams')}
            />
          </div>
          <div>
            <label className="form-label">Ширина упаковки, мм</label>
            <input
              className="form-input"
              type="number"
              value={form.package_width_mm ?? ''}
              onChange={set('package_width_mm')}
            />
          </div>
          <div>
            <label className="form-label">Высота упаковки, мм</label>
            <input
              className="form-input"
              type="number"
              value={form.package_height_mm ?? ''}
              onChange={set('package_height_mm')}
            />
          </div>
          <div>
            <label className="form-label">Длина упаковки, мм</label>
            <input
              className="form-input"
              type="number"
              value={form.package_length_mm ?? ''}
              onChange={set('package_length_mm')}
            />
          </div>
          <div>
            <label className="form-label">Бренд по умолчанию</label>
            <input
              className="form-input"
              value={form.brand || ''}
              onChange={set('brand')}
              placeholder="Нет бренда"
            />
          </div>
          <div>
            <label className="form-label">Нужен код маркировки</label>
            <select className="form-input" value={form.marking || 'Нет'} onChange={set('marking')}>
              <option value="Нет">Нет</option>
              <option value="Да">Да</option>
            </select>
          </div>
        </div>

        <p className="form-hint" style={{ marginTop: '0.6rem' }}>
          Эти значения подставляются ТОЛЬКО в пустые поля товаров — уже заполненные данные не
          перезаписываются. Атрибуты «Тип», «Модель», «Бренд», «Маркировка» дописываются
          автоматически при миграции (Тип выводится из категории: «Одежда / Футболка» → «Футболка»).
        </p>

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>
            Закрыть
          </Button>
          <Button onClick={handleSave} loading={loading}>
            <Icon name="save" size={16} /> Сохранить дефолты
          </Button>
        </div>
      </div>
    </div>
  );
};

export default DefaultsModal;
