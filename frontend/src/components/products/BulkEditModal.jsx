import React, { useState } from 'react';
import Button from '../common/Button';
import Icon from '../icons';

const BulkEditModal = ({ isOpen, onClose, selectedIds, onSubmit, loading }) => {
  const [applyPrice, setApplyPrice] = useState(true);
  const [priceMode, setPriceMode] = useState('fixed'); // percent | fixed
  const [percent, setPercent] = useState('15');
  const [fixedPrice, setFixedPrice] = useState('990');
  const [applyBrand, setApplyBrand] = useState(false);
  const [brand, setBrand] = useState('');
  const [applyCategory, setApplyCategory] = useState(false);
  const [category, setCategory] = useState('');

  if (!isOpen) return null;

  const submit = () => {
    if (!applyPrice && !applyBrand && !applyCategory) {
      alert('Отметьте хотя бы одно поле для обновления');
      return;
    }
    const payload = { product_ids: selectedIds };
    if (applyPrice) {
      if (priceMode === 'percent') {
        payload.price_percent = parseFloat(percent) || 0;
      } else {
        payload.price = parseFloat(fixedPrice) || 0;
      }
    }
    if (applyBrand) payload.brand = brand;
    if (applyCategory) payload.category = category;
    onSubmit(payload);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="edit" size={22} />
            Массовое редактирование
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Будет обновлено товаров: <b>{selectedIds.length}</b>. Отметьте поля, которые нужно изменить.
        </p>

        {/* Цена */}
        <div className="bulk-edit-row">
          <label className="bulk-check">
            <input
              type="checkbox"
              checked={applyPrice}
              onChange={(e) => setApplyPrice(e.target.checked)}
            />
            Цена
          </label>
          {applyPrice && (
            <div className="bulk-edit-fields">
              <div className="import-method-toggle" style={{ marginBottom: '0.5rem' }}>
                <button
                  className={`toggle-btn ${priceMode === 'fixed' ? 'active' : ''}`}
                  onClick={() => setPriceMode('fixed')}
                >
                  Фиксированная
                </button>
                <button
                  className={`toggle-btn ${priceMode === 'percent' ? 'active' : ''}`}
                  onClick={() => setPriceMode('percent')}
                >
                  Наценка, %
                </button>
              </div>
              {priceMode === 'fixed' ? (
                <input
                  className="form-input"
                  type="number"
                  value={fixedPrice}
                  onChange={(e) => setFixedPrice(e.target.value)}
                  placeholder="Одна цена для всех"
                />
              ) : (
                <input
                  className="form-input"
                  type="number"
                  value={percent}
                  onChange={(e) => setPercent(e.target.value)}
                  placeholder="Например, 15"
                />
              )}
            </div>
          )}
        </div>

        {/* Бренд */}
        <div className="bulk-edit-row">
          <label className="bulk-check">
            <input
              type="checkbox"
              checked={applyBrand}
              onChange={(e) => setApplyBrand(e.target.checked)}
            />
            Бренд
          </label>
          {applyBrand && (
            <input
              className="form-input"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="Например, МояФабрика"
            />
          )}
        </div>

        {/* Категория */}
        <div className="bulk-edit-row">
          <label className="bulk-check">
            <input
              type="checkbox"
              checked={applyCategory}
              onChange={(e) => setApplyCategory(e.target.checked)}
            />
            Категория
          </label>
          {applyCategory && (
            <input
              className="form-input"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="Например, Одежда > Футболки"
            />
          )}
        </div>

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button onClick={submit} disabled={loading} loading={loading}>
            Применить
          </Button>
        </div>
      </div>
    </div>
  );
};

export default BulkEditModal;