import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { api } from '../../api';

const MigrateModal = ({ isOpen, onClose, product, onConfirm, loading }) => {
  const [platform, setPlatform] = useState('ozon');
  const [edited, setEdited] = useState(null);

  useEffect(() => {
    if (isOpen && product) {
      setEdited({
        name: product.name || '',
        price: product.price ?? '',
        category: product.mapped_category || product.category || '',
      });
    }
  }, [isOpen, product]);

  if (!isOpen || !product) return null;

  const handleChange = (field, value) =>
    setEdited((e) => ({ ...e, [field]: value }));

  const handleConfirm = () => onConfirm(product.id, platform, edited);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="migrate" size={22} /> Миграция карточки
          </h2>
          <button className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={14} />
          </button>
        </div>

        {/* Карточка товара */}
        <div className="migrate-product-card">
          <div className="product-name">{product.name}</div>
          <div className="product-sub">
            {product.sku && <>SKU: {product.sku} · </>}
            {product.brand || 'Без бренда'}
            {product.price ? ` · ${Number(product.price).toLocaleString('ru-RU')} ₽` : ''}
          </div>
        </div>

        {/* Площадка */}
        <label className="form-label">Целевая площадка:</label>
        <div className="platform-selector">
          {PLATFORMS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`platform-btn ${platform === p.id ? 'platform-btn-active' : ''}`}
              onClick={() => setPlatform(p.id)}
            >
              {p.name}
            </button>
          ))}
        </div>

        {/* Редактируемые поля */}
        <label className="form-label">Данные карточки (можно править):</label>

        <label className="form-label">Название</label>
        <input
          className="form-input"
          value={edited?.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
        />

        <label className="form-label">Цена, ₽</label>
        <input
          className="form-input"
          type="number"
          value={edited?.price ?? ''}
          onChange={(e) => handleChange('price', e.target.value)}
        />

        <label className="form-label">Категория</label>
        <input
          className="form-input"
          value={edited?.category || ''}
          onChange={(e) => handleChange('category', e.target.value)}
        />

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button onClick={handleConfirm} disabled={loading} loading={loading}>
            <Icon name="migrate" size={16} /> Мигрировать
          </Button>
        </div>
      </div>
    </div>
  );
};

export default MigrateModal;