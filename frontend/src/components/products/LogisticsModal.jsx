import React, { useState, useEffect, useCallback } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api } from '../../api';
import TnvedSelector from './TnvedSelector';

// Значения НДС как в XLS-шаблонах площадок
const VAT_OPTIONS = [
  { value: 'none', label: 'Не облагается' },
  { value: '22', label: '22' },
  { value: '10', label: '10' },
  { value: '7', label: '7' },
  { value: '5', label: '5' },
];

const DEFAULT_FORM = {
  barcode: '',
  weight_grams: '',
  package_weight_grams: '',
  package_width_mm: '',
  package_height_mm: '',
  package_length_mm: '',
  vat_rate: '',
  okpd_code: '',
  units_per_item: 1,
};

const num = (v) => (v === '' || v == null ? null : Number(v));

/**
 * Генерирует валидный 13-значный штрихкод EAN-13 (префикс 200 + контрольная цифра по алгоритму GS1).
 */
const generateValidEan13 = (productId) => {
  const pid = Number(productId) || Math.floor(Math.random() * 999999);
  const randPart = String(Math.floor(100 + Math.random() * 900));
  const base12 = (`200${String(pid).padStart(6, '0')}${randPart}`).slice(0, 12);
  let oddSum = 0;
  let evenSum = 0;
  for (let i = 0; i < 12; i++) {
    const digit = Number(base12[i]);
    if (i % 2 === 0) oddSum += digit;
    else evenSum += digit;
  }
  const checkDigit = (10 - ((oddSum + evenSum * 3) % 10)) % 10;
  return `${base12}${checkDigit}`;
};

const LogisticsModal = ({ isOpen, onClose, product, onSaved }) => {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen || !product) return;
    setForm({
      barcode: product.barcode ?? '',
      weight_grams: product.weight_grams ?? '',
      package_weight_grams: product.package_weight_grams ?? '',
      package_width_mm: product.package_width_mm ?? '',
      package_height_mm: product.package_height_mm ?? '',
      package_length_mm: product.package_length_mm ?? '',
      vat_rate: product.vat_rate ?? '',
      okpd_code: product.okpd_code ?? '',
      units_per_item: product.units_per_item ?? 1,
    });
    setError('');
  }, [isOpen, product?.id, product]);

  useEffect(() => {
    if (!isOpen) setError('');
  }, [isOpen]);

  const set = useCallback(
    (key) => (e) => {
      setForm((f) => ({ ...f, [key]: e.target.value }));
    },
    []
  );

  const handleGenerateBarcode = useCallback(() => {
    const ean = generateValidEan13(product?.id);
    setForm((f) => ({ ...f, barcode: ean }));
  }, [product?.id]);

  if (!isOpen || !product) return null;

  const mainPhoto = (product.photos || [])[0] || '';

  const missingRequired = [];
  if (!form.vat_rate) missingRequired.push('НДС, %');
  if (!form.okpd_code) missingRequired.push('ТН ВЭД коды ЕАЭС');
  if (!num(form.package_weight_grams)) missingRequired.push('Вес в упаковке, г');
  if (!num(form.package_width_mm)) missingRequired.push('Ширина упаковки, мм');
  if (!num(form.package_height_mm)) missingRequired.push('Высота упаковки, мм');
  if (!num(form.package_length_mm)) missingRequired.push('Длина упаковки, мм');
  if (!mainPhoto) missingRequired.push('Ссылка на главное фото (окно «Фото»)');

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      await api.updateProductLogistics(product.id, {
        barcode: form.barcode ? String(form.barcode).trim() : null,
        weight_grams: num(form.weight_grams),
        package_weight_grams: num(form.package_weight_grams),
        package_width_mm: num(form.package_width_mm),
        package_height_mm: num(form.package_height_mm),
        package_length_mm: num(form.package_length_mm),
        vat_rate: form.vat_rate || null,
        okpd_code: form.okpd_code || null,
        units_per_item: num(form.units_per_item) ?? 1,
      });

      if (onSaved) {
        try {
          await onSaved();
        } catch (e) {
          console.warn('onSaved failed:', e);
        }
      }

      onClose();
    } catch (e) {
      setError(`Ошибка сохранения: ${e.message || 'Неизвестная ошибка'}`);
    } finally {
      setSaving(false);
    }
  };

  const req = <span style={{ color: 'var(--accent-danger)', fontWeight: 700 }}> *</span>;

  return (
    <div className="modal-overlay" onClick={saving ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="box" size={22} /> Логистика и налоги
          </h2>
          <button
            type="button"
            className="close-btn"
            onClick={onClose}
            disabled={saving}
            title="Закрыть"
          >
            <Icon name="close" size={16} />
          </button>
        </div>

        <p className="form-hint" style={{ marginBottom: '0.75rem' }}>
          Поля со звёздочкой <span style={{ color: 'var(--accent-danger)' }}>*</span> обязательны в
          XLS-шаблонах Ozon и Яндекс Маркета. При выгрузке на Яндекс Маркет граммы и миллиметры
          автоматически пересчитываются в килограммы и сантиметры.
        </p>

        {/* ================= Налоги ================= */}
        <label className="form-label">НДС, %{req}</label>
        <select
          className="form-input"
          value={form.vat_rate}
          onChange={set('vat_rate')}
          disabled={saving}
        >
          <option value="">— не указано —</option>
          {VAT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <p className="form-hint">
          Значения: «Не облагается» (УСН), 22, 10, 7, 5.
        </p>

        {/* ================= ТН ВЭД (Умный селектор) ================= */}
        <label className="form-label">ТН ВЭД коды ЕАЭС{req}</label>
        <TnvedSelector
          value={form.okpd_code}
          onChange={(val) => setForm((f) => ({ ...f, okpd_code: val }))}
          productName={product.name}
          category={product.mapped_category || product.category || ''}
          disabled={saving}
        />
        <p className="form-hint">
          Обязателен в шаблонах Ozon и Яндекс Маркета. Начните вводить название товара выше для автоподбора.
        </p>

        {/* ================= Габариты упаковки (ОВХ) ================= */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '0.5rem',
            marginTop: '0.5rem',
          }}
        >
          <div>
            <label className="form-label">Вес в упаковке, г{req}</label>
            <input
              className="form-input"
              type="number"
              min="1"
              value={form.package_weight_grams}
              onChange={set('package_weight_grams')}
              disabled={saving}
            />
          </div>
          <div>
            <label className="form-label">Вес товара, г</label>
            <input
              className="form-input"
              type="number"
              min="1"
              value={form.weight_grams}
              onChange={set('weight_grams')}
              disabled={saving}
            />
          </div>
          <div>
            <label className="form-label">Ширина упаковки, мм{req}</label>
            <input
              className="form-input"
              type="number"
              min="1"
              value={form.package_width_mm}
              onChange={set('package_width_mm')}
              disabled={saving}
            />
          </div>
          <div>
            <label className="form-label">Высота упаковки, мм{req}</label>
            <input
              className="form-input"
              type="number"
              min="1"
              value={form.package_height_mm}
              onChange={set('package_height_mm')}
              disabled={saving}
            />
          </div>
          <div>
            <label className="form-label">Длина упаковки, мм{req}</label>
            <input
              className="form-input"
              type="number"
              min="1"
              value={form.package_length_mm}
              onChange={set('package_length_mm')}
              disabled={saving}
            />
          </div>
          <div>
            <label className="form-label">Единиц в одном товаре</label>
            <input
              className="form-input"
              type="number"
              min="1"
              value={form.units_per_item}
              onChange={set('units_per_item')}
              disabled={saving}
            />
          </div>
        </div>
        <p className="form-hint">
          Указывайте в граммах и миллиметрах (для Яндекс Маркета перевод в кг и см выполняется автоматически).
        </p>

        {/* ================= Штрихкод (обязателен для Яндекса, опционален для Ozon) ================= */}
        <label className="form-label">
          Штрихкод (Серийный номер / EAN){' '}
          <span style={{ color: 'var(--accent-warning)', fontSize: '0.8rem', fontWeight: 500 }}>
            (обязателен для Яндекс Маркета и WB)
          </span>
        </label>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            className="form-input"
            style={{ flex: 1 }}
            type="text"
            value={form.barcode}
            onChange={set('barcode')}
            placeholder="Например: 4607001234567 или нажмите «Сгенерировать»"
            disabled={saving}
          />
          <Button
            type="button"
            variant="secondary"
            onClick={handleGenerateBarcode}
            disabled={saving}
            title="Сгенерировать валидный 13-значный штрихкод EAN-13"
          >
            🎲 Сгенерировать EAN-13
          </Button>
        </div>
        <p className="form-hint">
          ⚠️ В шаблоне <strong>Яндекс Маркета</strong> колонка «Штрихкод *» обязательна (если оставить пустым,
          при выгрузке на Яндекс система сгенерирует валидный EAN-13 автоматически). В шаблоне{' '}
          <strong>Ozon</strong> поле необязательное.
        </p>

        {/* ================= Индикатор главного фото ================= */}
        <div
          className={`alert ${mainPhoto ? 'alert-success' : 'alert-error'}`}
          style={{ marginTop: '0.75rem' }}
        >
          <div>
            {mainPhoto ? (
              <>✅ Ссылка на главное фото* установлена: {String(mainPhoto).slice(0, 60)}…</>
            ) : (
              <>
                ❌ Ссылка на главное фото* не установлена — поле обязательное в шаблонах Ozon и
                Яндекс Маркета. Добавьте фото в окне «Фото».
              </>
            )}
          </div>
        </div>

        {/* ================= Предупреждение о недостающих обязательных ================= */}
        {missingRequired.length > 0 && (
          <div className="alert alert-error" style={{ marginTop: '0.5rem' }}>
            <div>
              Не заполнены обязательные поля шаблона:{' '}
              <strong>{missingRequired.join(', ')}</strong>. Сохранить можно, но товар не попадёт в
              выгрузку до заполнения.
            </div>
          </div>
        )}

        {error && (
          <div className="alert alert-error" style={{ marginTop: '0.5rem' }}>
            <div>{error}</div>
          </div>
        )}

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Отмена
          </Button>
          <Button onClick={handleSave} loading={saving} disabled={saving}>
            <Icon name="save" size={16} /> Сохранить
          </Button>
        </div>
      </div>
    </div>
  );
};

export default LogisticsModal;