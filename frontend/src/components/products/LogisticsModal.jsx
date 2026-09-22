import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api } from '../../api';

const VAT_OPTIONS = [
  { value: 'none', label: 'Не облагается (УСН)' },
  { value: '10', label: '10%' },
  { value: '22', label: '22%' },
];

const numOrNull = (v) => (v === '' || v === null || v === undefined ? null : Number(v));

const LogisticsModal = ({ isOpen, onClose, product, onSaved }) => {
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen && product) {
      setForm({
        barcode: product.barcode || '',
        weight_grams: product.weight_grams ?? '',
        package_weight_grams: product.package_weight_grams ?? '',
        package_width_mm: product.package_width_mm ?? '',
        package_height_mm: product.package_height_mm ?? '',
        package_length_mm: product.package_length_mm ?? '',
        vat_rate: product.vat_rate || 'none',
        okpd_code: product.okpd_code || '',
        units_per_item: product.units_per_item ?? 1,
      });
      setError('');
    }
  }, [isOpen, product]);

  if (!isOpen || !product) return null;

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await api.updateLogistics(product.id, {
        barcode: form.barcode || null,
        weight_grams: numOrNull(form.weight_grams),
        package_weight_grams: numOrNull(form.package_weight_grams),
        package_width_mm: numOrNull(form.package_width_mm),
        package_height_mm: numOrNull(form.package_height_mm),
        package_length_mm: numOrNull(form.package_length_mm),
        vat_rate: form.vat_rate || null,
        okpd_code: form.okpd_code || null,
        units_per_item: numOrNull(form.units_per_item) ?? 1,
      });
      if (onSaved) onSaved();
      onClose();
    } catch (err) {
      setError(err.message || 'Ошибка сохранения');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="box" size={22} /> Логистика и налоги
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <div className="migrate-product-card">
          <div className="product-name">{product.name}</div>
          <div className="product-sub">
            {product.sku && <>арт: {product.sku} · </>}
            {product.source}
          </div>
        </div>

        {error && <div className="alert alert-error"><div>{error}</div></div>}

        <form onSubmit={submit}>
          <label className="form-label">Штрихкод (EAN) *</label>
          <input className="form-input" value={form.barcode || ''} onChange={set('barcode')} placeholder="4600000000000" />
          <p className="form-hint">Обязателен для всех схем продаж Ozon. Несколько кодов — через точку с запятой.</p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div>
              <label className="form-label">Вес товара, г</label>
              <input className="form-input" type="number" min="0" value={form.weight_grams ?? ''} onChange={set('weight_grams')} placeholder="606" />
            </div>
            <div>
              <label className="form-label">Вес в упаковке, г *</label>
              <input className="form-input" type="number" min="0" value={form.package_weight_grams ?? ''} onChange={set('package_weight_grams')} placeholder="700" />
            </div>
            <div>
              <label className="form-label">Ширина упаковки, мм *</label>
              <input className="form-input" type="number" min="0" value={form.package_width_mm ?? ''} onChange={set('package_width_mm')} placeholder="200" />
            </div>
            <div>
              <label className="form-label">Высота упаковки, мм *</label>
              <input className="form-input" type="number" min="0" value={form.package_height_mm ?? ''} onChange={set('package_height_mm')} placeholder="50" />
            </div>
            <div>
              <label className="form-label">Длина упаковки, мм *</label>
              <input className="form-input" type="number" min="0" value={form.package_length_mm ?? ''} onChange={set('package_length_mm')} placeholder="300" />
            </div>
            <div>
              <label className="form-label">Единиц в одном товаре</label>
              <input className="form-input" type="number" min="1" value={form.units_per_item ?? 1} onChange={set('units_per_item')} />
            </div>
          </div>
          <p className="form-hint">Только числа, без единиц измерения. Для поштучной продажи укажите «1».</p>

          <label className="form-label">Ставка НДС</label>
          <select className="form-input" value={form.vat_rate || 'none'} onChange={set('vat_rate')}>
            {VAT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <p className="form-hint">«Не облагается» — для УСН. Если не указать, Ozon подставит «Не облагается» автоматически.</p>

          <label className="form-label">Код ОКПД / ТН ВЭД</label>
          <input className="form-input" value={form.okpd_code || ''} onChange={set('okpd_code')} placeholder="14.13.00.000" />
          <p className="form-hint">
            Обязательно для маркируемых категорий: одежда, обувь, шубы, лекарства, духи, шины,
            товары лёгкой промышленности, фотоаппараты и лампы-вспышки («Честный ЗНАК»).
          </p>

          <div className="modal-actions">
            <Button variant="outline" type="button" onClick={onClose}>Отмена</Button>
            <Button type="submit" disabled={loading} loading={loading}>
              <Icon name="save" size={16} /> Сохранить
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default LogisticsModal;