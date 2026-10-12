import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api } from '../../api';

const PhotosModal = ({ isOpen, onClose, product, onSave, onNotify }) => {
  const [photos, setPhotos] = useState([]);
  const [newUrl, setNewUrl] = useState('');
  const [dragIdx, setDragIdx] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setPhotos(product?.photos || []);
      setNewUrl('');
      setDragIdx(null);
    }
  }, [isOpen, product]);

  if (!isOpen || !product) return null;

  const notify = (msg) => onNotify && onNotify(msg);

  /* ---------- drag-and-drop сортировка ---------- */

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

  /* ---------- операции ---------- */

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
      notify('✅ Порядок и состав фото сохранены');
      if (onSave) onSave();
      onClose();
    } catch (e) {
      notify('❌ ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const data = await api.downloadPhotos(product.id);
      notify(`Скачивание запущено в фоне (${data.photos} фото)`);
    } catch (e) {
      notify('❌ ' + e.message);
    } finally {
      setDownloading(false);
    }
  };

  /* ---------- рендер ---------- */

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="photo" size={22} /> Фото: {product.name}
          </h2>
          <button className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={14} />
          </button>
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
                  <button
                    type="button"
                    title="Сделать главным"
                    disabled={idx === 0}
                    onClick={() => handleMakeMain(idx)}
                  >
                    <Icon name="star" size={13} />
                  </button>
                  <button type="button" title="Удалить" onClick={() => handleRemove(idx)}>
                    <Icon name="trash" size={13} />
                  </button>
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
          <Button
            variant="secondary"
            onClick={handleAdd}
            disabled={!newUrl.trim().startsWith('http')}
          >
            <Icon name="plus" size={14} /> Добавить
          </Button>
        </div>

        <div className="modal-actions">
          <Button
            variant="outline"
            onClick={handleDownload}
            disabled={downloading || photos.length === 0}
            loading={downloading}
          >
            <Icon name="import" size={16} /> Скачать копии
          </Button>
          <div style={{ flex: 1 }} />
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={handleSave} disabled={loading} loading={loading}>
            <Icon name="check" size={16} /> Сохранить ({photos.length})
          </Button>
        </div>
      </div>
    </div>
  );
};

export default PhotosModal;
