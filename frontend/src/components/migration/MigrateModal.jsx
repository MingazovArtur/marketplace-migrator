import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import { PLATFORMS, detectPlatform } from '../../utils/platformUtils';
import { MigrateIcon } from '../icons/Icons';
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
      <div className="modal modal-migrate" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-header-left">
            <div className="modal-icon">
              <MigrateIcon size={24} />
            </div>
            <h2 className="modal-title">Перенос товара</h2>
          </div>
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
            <p className="modal-subtitle">Выберите целевую платформу для переноса:</p>
            <div className="platform-selector">
              {availablePlatforms.map(p => (
                <button
                  key={p.id}
                  className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => setSelectedPlatform(p.id)}
                  data-platform={p.id}
                >
                  <div className="platform-logo" style={{
                    backgroundColor: selectedPlatform === p.id ? p.color : 'var(--bg-tertiary)',
                    color: selectedPlatform === p.id ? 'white' : 'var(--text-muted)'
                  }}>
                    {p.logoText}
                  </div>
                  <span>{p.name}</span>
                </button>
              ))}
            </div>
            <div className="modal-actions">
              <Button variant="outline" onClick={onClose}>Отмена</Button>
              <Button onClick={handleLoadPreview} disabled={previewLoading || !selectedPlatform} loading={previewLoading}>
                Показать предпросмотр
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="migrate-comparison">
              {/* Карточка "Было" */}
              <div className="migrate-card migrate-card-source">
                <div className="migrate-card-header">
                  <span className="migrate-card-label">Было</span>
                  <span className="migrate-card-platform" style={{ color: PLATFORMS.find(p => p.id === currentPlatform)?.color }}>
                    {PLATFORMS.find(p => p.id === currentPlatform)?.name}
                  </span>
                </div>
                <div className="migrate-card-body">
                  <div className="migrate-field">
                    <label>Название</label>
                    <div className="migrate-value">{previewData.original.name}</div>
                  </div>
                  <div className="migrate-field">
                    <label>Цена</label>
                    <div className="migrate-value migrate-price">{previewData.original.price} ₽</div>
                  </div>
                  <div className="migrate-field">
                    <label>Категория</label>
                    <div className="migrate-value">{previewData.original.category}</div>
                  </div>
                </div>
              </div>

              {/* Стрелка */}
              <div className="migrate-arrow">→</div>

              {/* Карточка "Станет" с редактированием */}
              <div className="migrate-card migrate-card-target">
                <div className="migrate-card-header">
                  <span className="migrate-card-label">Станет</span>
                  <span className="migrate-card-platform" style={{ color: PLATFORMS.find(p => p.id === selectedPlatform)?.color }}>
                    {PLATFORMS.find(p => p.id === selectedPlatform)?.name}
                  </span>
                </div>
                <div className="migrate-card-body">
                  <div className="migrate-field migrate-field-editable">
                    <label>Название</label>
                    <textarea
                      className="migrate-input migrate-textarea"
                      value={previewData.target.name}
                      onChange={(e) => setPreviewData({ ...previewData, target: { ...previewData.target, name: e.target.value } })}
                      rows={2}
                    />
                  </div>
                  <div className="migrate-field migrate-field-editable">
                    <label>Цена</label>
                    <div className="migrate-price-input-wrapper">
                      <input
                        type="number"
                        className="migrate-input migrate-price-input"
                        value={previewData.target.price}
                        onChange={(e) => {
                          const newPrice = parseFloat(e.target.value) || 0;
                          const originalPrice = previewData.original.price;
                          const percentChange = originalPrice > 0 ? ((newPrice - originalPrice) / originalPrice * 100).toFixed(0) : 0;
                          setPreviewData({ ...previewData, target: { ...previewData.target, price: newPrice, priceChangePercent: percentChange } });
                        }}
                        step="0.01"
                        min="0"
                      />
                      {previewData.target.priceChangePercent > 0 && (
                        <span className="migrate-price-badge">+{previewData.target.priceChangePercent}%</span>
                      )}
                    </div>
                  </div>
                  <div className="migrate-field migrate-field-editable">
                    <label>Категория</label>
                    <input
                      type="text"
                      className="migrate-input"
                      value={previewData.target.category}
                      onChange={(e) => setPreviewData({ ...previewData, target: { ...previewData.target, category: e.target.value } })}
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="migrate-hint">
              <span className="hint-icon">✏️</span>
              <p>{previewData.mapping_reason || 'Вы можете изменить данные перед переносом.'}</p>
            </div>

            <div className="modal-actions">
              <Button variant="outline" onClick={() => setPreviewData(null)}>← Назад</Button>
              <Button onClick={handleConfirm} disabled={loading} loading={loading}>
                Подтвердить и перенести
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default MigrateModal;