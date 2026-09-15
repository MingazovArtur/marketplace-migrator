import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import { PLATFORMS, detectPlatform } from '../../utils/platformUtils';
import { api } from '../../api';

const MigrateModal = ({ isOpen, onClose, product, onConfirm, loading }) => {
  const [selectedPlatform, setSelectedPlatform] = useState('');
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen && product) {
      const currentPlatform = detectPlatform(product?.source);
      const available = PLATFORMS.filter(p => p.id !== currentPlatform);
      setSelectedPlatform(available[0]?.id || '');
      setPreviewData(null);
      setError('');
    }
  }, [isOpen, product]);

  if (!isOpen || !product) return null;

  const currentPlatform = detectPlatform(product.source);
  const availablePlatforms = PLATFORMS.filter(p => p.id !== currentPlatform);

  const handleLoadPreview = async () => {
    if (!selectedPlatform) return;
    setPreviewLoading(true);
    setError('');
    try {
      const data = await api.previewMigration(product.id, selectedPlatform);
      setPreviewData(data.preview);
    } catch (err) {
      setError(err.message || 'Не удалось загрузить предпросмотр');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleConfirm = () => {
    if (!previewData) return;
    onConfirm(product.id, selectedPlatform, {
      name: previewData.target.name,
      price: previewData.target.price,
      category: previewData.target.category
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-preview" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>🔄 Перенос товара</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        {error && (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            {error}
            <button onClick={() => setError('')} className="alert-close">✕</button>
          </div>
        )}

        {!previewData ? (
          <>
            <p className="modal-text">Выберите целевую платформу:</p>
            <div className="platform-selector">
              {availablePlatforms.map(p => (
                <button
                  key={p.id}
                  className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => setSelectedPlatform(p.id)}
                  data-platform={p.id}
                >
                  <div className="platform-logo" style={{
                    backgroundColor: selectedPlatform === p.id ? p.color : '#f1f5f9',
                    color: selectedPlatform === p.id ? 'white' : '#64748b'
                  }}>
                    {p.logoText}
                  </div>
                  <span>{p.name}</span>
                </button>
              ))}
            </div>
            <div className="modal-actions">
              <Button variant="outline" onClick={onClose}>Отмена</Button>
              <Button onClick={handleLoadPreview} disabled={previewLoading || !selectedPlatform}>
                {previewLoading ? '⏳ Загрузка...' : '👁️ Показать предпросмотр'}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="preview-comparison">
              <div className="preview-card original">
                <h3>📦 Было (Источник)</h3>
                <div className="preview-row"><span className="label">Название:</span><span className="value">{previewData.original.name}</span></div>
                <div className="preview-row"><span className="label">Цена:</span><span className="value price">{previewData.original.price} ₽</span></div>
                <div className="preview-row"><span className="label">Категория:</span><span className="value">{previewData.original.category}</span></div>
              </div>
              <div className="preview-arrow">➜</div>
              <div className="preview-card target editable">
                <h3>🎯 Станет ({PLATFORMS.find(p => p.id === selectedPlatform)?.name})</h3>
                <div className="preview-row editable-row">
                  <span className="label">Название:</span>
                  <textarea
                    className="editable-input"
                    value={previewData.target.name}
                    onChange={(e) => setPreviewData({ ...previewData, target: { ...previewData.target, name: e.target.value } })}
                    rows={3}
                  />
                </div>
                <div className="preview-row editable-row">
                  <span className="label">Цена:</span>
                  <div className="price-input-wrapper">
                    <input
                      type="number"
                      className="editable-input price-input"
                      value={previewData.target.price}
                      onChange={(e) => {
                        const newPrice = parseFloat(e.target.value) || 0;
                        const originalPrice = previewData.original.price;
                        const percentChange = ((newPrice - originalPrice) / originalPrice * 100).toFixed(0);
                        setPreviewData({ ...previewData, target: { ...previewData.target, price: newPrice, priceChangePercent: percentChange } });
                      }}
                      step="0.01"
                      min="0"
                    />
                    {previewData.target.priceChangePercent > 0 && (
                      <span className="badge badge-success" style={{ fontSize: '0.7em', marginLeft: '5px' }}>
                        +{previewData.target.priceChangePercent}%
                      </span>
                    )}
                  </div>
                </div>
                <div className="preview-row editable-row">
                  <span className="label">Категория:</span>
                  <input
                    type="text"
                    className="editable-input"
                    value={previewData.target.category}
                    onChange={(e) => setPreviewData({ ...previewData, target: { ...previewData.target, category: e.target.value } })}
                  />
                </div>
              </div>
            </div>
            <div className="modal-hint-box" style={{ marginTop: '1.5rem' }}>
              <span className="hint-icon">✏️</span>
              <p>{previewData.mapping_reason || 'Вы можете изменить данные перед переносом.'}</p>
            </div>
            <div className="modal-actions">
              <Button variant="outline" onClick={() => setPreviewData(null)}>← Выбрать другую платформу</Button>
              <Button onClick={handleConfirm} disabled={loading}>
                {loading ? '⏳ Перенос...' : '✅ Подтвердить и перенести'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default MigrateModal;