import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import { api } from '../../api';

const PhotosModal = ({ isOpen, onClose, product, onSave, onNotify }) => {
  const [photos, setPhotos] = useState([]);
  const [newUrl, setNewUrl] = useState('');
  const [dragIdx, setDragIdx] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (isOpen && product) setPhotos(product.photos || []);
  }, [isOpen, product]);

  if (!isOpen || !product) return null;

  const handleDragStart = (idx) => setDragIdx(idx);

  const handleDragOver = (e, idx) => {
    e.preventDefault();
    if (dragIdx === null || dragIdx === idx) return;
    const updated = [...photos];
    const [moved] = updated.splice(dragIdx, 1);
    updated.splice(idx, 0, moved);
    setDragIdx(idx);
    setPhotos(updated);
  };

  const handleDragEnd = () => setDragIdx(null);

  const handleMakeMain = (idx) => {
    const updated = [...photos];
    const [moved] = updated.splice(idx, 1);
    updated.unshift(moved);
    setPhotos(updated);
  };

  const handleRemove = (idx) => setPhotos(photos.filter((_, i) => i !== idx));

  const handleAdd = () => {
    const url = newUrl.trim();
    if (!url.startsWith('http') || photos.includes(url)) return;
    setPhotos([...photos, url]);
    setNewUrl('');
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      await api.setPhotos(product.id, photos);
      onNotify && onNotify('✅ Порядок и состав фото сохранены');
      onSave && onSave();
      onClose();
    } catch (e) {
      onNotify && onNotify('❌ ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const data = await api.downloadPhotos(product.id);
      onNotify && onNotify(`💾 Скачивание запущено в фоне (${data.photos} фото)`);
    } catch (e) {
      onNotify && onNotify('❌ ' + e.message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">🖼 Фото: {product.name}</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <p style={{ color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
          Перетаскивайте фото, чтобы изменить порядок. Первое фото — главное в карточке площадки.
        </p>

        {photos.length === 0 ? (
          <div className="empty-state" style={{ padding: '1.5rem' }}>
            <div className="empty-state-icon">🖼</div>
            <p className="empty-state-text">Фото нет. Добавьте ссылки ниже.</p>
          </div>
        ) : (
          <div className="photos-grid">
            {photos.map((url, idx) => (
              <div
                key={`${idx}-${url}`}
                className={`photo-card ${dragIdx === idx ? 'dragging' : ''}`}
                draggable
                onDragStart={() => handleDragStart(idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragEnd={handleDragEnd}
              >
                <img
                  src={url}
                  alt={`Фото ${idx + 1}`}
                  loading="lazy"
                  onError={(e) => e.target.classList.add('img-error')}
                />
                <span className="photo-idx">{idx + 1}</span>
                {idx === 0 && <span className="photo-main-badge">Главное</span>}
                <div className="photo-actions">
                  <button title="Сделать главным" onClick={() => handleMakeMain(idx)} disabled={idx === 0}>
                    ⭐
                  </button>
                  <button title="Удалить" onClick={() => handleRemove(idx)}>🗑</button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="photos-add-row">
          <input
            className="form-input"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            placeholder="https://example.com/photo.jpg"
          />
          <Button variant="secondary" onClick={handleAdd} disabled={!newUrl.trim().startsWith('http')}>
            + Добавить
          </Button>
        </div>

        <div className="modal-actions">
          <Button
            variant="outline"
            onClick={handleDownload}
            disabled={downloading || photos.length === 0}
            loading={downloading}
          >
            💾 Скачать копии
          </Button>
          <div style={{ flex: 1 }} />
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button onClick={handleSave} disabled={loading} loading={loading}>
            Сохранить ({photos.length})
          </Button>
        </div>
      </div>
    </div>
  );
};

export default PhotosModal;