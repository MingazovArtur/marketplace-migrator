import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { useCategoryMappingCheck } from '../../hooks/useCategoryMapping';

const MigrateModal = ({ isOpen, onClose, product, onConfirm, loading }) => {
  const [platform, setPlatform] = useState('ozon');
  const [autoExport, setAutoExport] = useState(true);
  const [edited, setEdited] = useState(null);

  /* ✅ Хук вызывается ДО early return — иначе нарушение правил хуков */
  const { checked, isMapped } = useCategoryMappingCheck(
    product?.source,
    platform,
    product?.category
  );

  useEffect(() => {
    if (isOpen && product) {
      setEdited({
        name: product.name || '',
        price: product.price ?? '',
        category: product.mapped_category || product.category || '',
      });
      setAutoExport(true);
    }
  }, [isOpen, product]);

  if (!isOpen || !product) return null;

  const sourceName = PLATFORMS.find((p) => p.id === product.source)?.name || product.source;
  const targetName = PLATFORMS.find((p) => p.id === platform)?.name || platform;

  const handleChange = (field, value) => setEdited((e) => ({ ...e, [field]: value }));
  const handleConfirm = () => onConfirm(product.id, platform, edited, autoExport);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="migrate" size={22} /> Миграция карточки
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <div className="migrate-product-card">
          <div className="product-name">{product.name}</div>
          <div className="product-sub">
            {product.sku && <>SKU: {product.sku} · </>}
            {product.brand || 'Без бренда'}
            {product.price ? ` · ${Number(product.price).toLocaleString('ru-RU')} ₽` : ''}
          </div>
        </div>

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

        {/* ✅ Предупреждение: категория источника не сопоставлена для выбранной пары */}
        {checked && !isMapped && product.category && (
          <div
            className="modal-hint-box"
            style={{
              borderColor: 'rgba(245, 158, 11, 0.4)',
              background: 'rgba(245, 158, 11, 0.08)',
            }}
          >
            <span className="hint-icon">
              <Icon name="warning" size={18} />
            </span>
            <p>
              Категория «{product.category}» не сопоставлена для перехода{' '}
              <strong>{sourceName} → {targetName}</strong>. При миграции будет использовано
              значение из поля «Категория» ниже. Настроить соответствие можно в разделе
              «Маппинг» (боковое меню).
            </p>
          </div>
        )}

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

        <label className="bulk-check" style={{ margin: '1rem 0 0' }}>
          <input
            type="checkbox"
            checked={autoExport}
            onChange={(e) => setAutoExport(e.target.checked)}
          />
          Сразу скачать файл для загрузки в кабинет {platform}
        </label>

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