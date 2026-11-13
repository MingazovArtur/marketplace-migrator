import React, { useState, useEffect, useRef } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api, API_URL } from '../../api';

const BACKEND_ORIGIN = API_URL.replace(/\/api\/?$/, '');

/**
 * Преобразует путь к фото для корректного отображения в браузере:
 * - относительные пути /media/... или products/... направляет на бэкенд
 * - внешние http(s) ссылки возвращает как есть (при ошибке загрузки сработает fallback на прокси)
 */
const resolveDisplayUrl = (rawUrl) => {
  if (!rawUrl) return '';
  const u = String(rawUrl).trim();
  if (u.startsWith('http://') || u.startsWith('https://')) {
    // Если в БД сохранился localhost:5173/media/..., перенаправляем на бэкенд
    if (u.includes(':5173/media/') && BACKEND_ORIGIN) {
      return `${BACKEND_ORIGIN}/media/${u.split('/media/')[1]}`;
    }
    return u;
  }
  if (u.startsWith('/media/')) {
    return `${BACKEND_ORIGIN}${u}`;
  }
  if (u.startsWith('products/')) {
    return `${BACKEND_ORIGIN}/media/${u}`;
  }
  return u;
};

/**
 * ✅ Round 8: миниатюра для галереи — WebP ≤ 320px (/media/thumbs/...),
 * генерируется бэкендом при первом запросе. Только для локальных копий
 * (products/..., /media/...): у внешних ссылок миниатюры нет — отдаём
 * как есть (при сбое CDN сработает прокси-fallback в handleImgError).
 */
const resolveThumbUrl = (rawUrl) => {
  if (!rawUrl) return '';
  const u = String(rawUrl).trim();
  const toThumb = (rel) => `${BACKEND_ORIGIN}/media/thumbs/${rel}`;
  if (u.startsWith('http://') || u.startsWith('https://')) {
    if (u.includes(':5173/media/') && BACKEND_ORIGIN) {
      return toThumb(u.split('/media/')[1]);
    }
    return u; // внешнее фото — миниатюры нет, только у локальных копий
  }
  if (u.startsWith('/media/')) {
    return toThumb(u.slice('/media/'.length));
  }
  if (u.startsWith('products/')) {
    return toThumb(u);
  }
  return u;
};

const buildProxyUrl = (rawUrl) => {
  if (!rawUrl) return '';
  const u = String(rawUrl).trim();
  if (!u.startsWith('http://') && !u.startsWith('https://')) return '';
  if (u.includes('/api/products/photos/proxy')) return '';
  return `${API_URL}/products/photos/proxy?url=${encodeURIComponent(u)}`;
};

const PhotosModal = ({ isOpen, onClose, product, onSave, onNotify }) => {
  const [photos, setPhotos] = useState([]);
  const [newUrl, setNewUrl] = useState('');
  const [dragIdx, setDragIdx] = useState(null);
  const [isFileDragging, setIsFileDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setPhotos(product?.photos || []);
      setNewUrl('');
      setDragIdx(null);
      setIsFileDragging(false);
    }
  }, [isOpen, product]);

  if (!isOpen || !product) return null;

  const notify = (msg) => onNotify && onNotify(msg);

  /* ---------- drag-and-drop сортировка карточек ---------- */

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

  /* ---------- загрузка файлов с компьютера ---------- */

  const handleUploadFiles = async (fileList) => {
    const files = Array.from(fileList || []).filter((f) => /\.(jpe?g|png|webp)$/i.test(f.name));
    if (files.length === 0) {
      notify('❌ Выберите изображения в формате JPG, PNG или WEBP');
      return;
    }

    setUploading(true);
    try {
      const data = await api.uploadProductPhotos(product.id, files);
      if (data?.photos) {
        setPhotos(data.photos);
      }
      notify(`✅ Загружено фото: ${data?.uploaded?.length || files.length}`);
      if (onSave) await onSave();
    } catch (e) {
      notify('❌ ' + e.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleContainerDrop = (e) => {
    e.preventDefault();
    setIsFileDragging(false);
    if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
      handleUploadFiles(e.dataTransfer.files);
    }
  };

  /* ---------- операции со ссылками ---------- */

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
      if (onSave) await onSave();
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
      if (data?.photos) {
        setPhotos(data.photos);
      }
      notify(
        `✅ Сохранены локальные копии фото (${data.downloaded ?? data.count ?? photos.length} шт.)`
      );
      if (onSave) await onSave();
    } catch (e) {
      notify('❌ ' + e.message);
    } finally {
      setDownloading(false);
    }
  };

  /* ---------- fallback при ошибке загрузки картинки ---------- */

  // Цепочка попыток (Round 8): миниатюра → оригинал → прокси → заглушка.
  // Первое звено новое: миниатюра могла не сгенерироваться (битый оригинал,
  // старый бэкенд без /media/thumbs) — тогда пробуем сам оригинал.
  const handleImgError = (e, rawUrl) => {
    const img = e.currentTarget;
    // Попытка 1: миниатюра не далась — грузим оригинал
    if (!img.dataset.triedOriginal) {
      img.dataset.triedOriginal = '1';
      const original = resolveDisplayUrl(rawUrl);
      if (original && original !== img.src) {
        img.src = original;
        return;
      }
    }
    // Попытка 2: если прямая ссылка заблокирована CDN, пробуем через наш backend-прокси
    if (!img.dataset.triedProxy) {
      const proxyUrl = buildProxyUrl(rawUrl);
      if (proxyUrl) {
        img.dataset.triedProxy = '1';
        img.src = proxyUrl;
        return;
      }
    }
    // Если даже прокси не помог (битая ссылка или 404 на источнике)
    img.classList.add('img-error');
  };

  /* ---------- рендер ---------- */

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal-wide"
        onClick={(e) => e.stopPropagation()}
        onDragOver={(e) => {
          if (e.dataTransfer?.types?.includes('Files')) {
            e.preventDefault();
            setIsFileDragging(true);
          }
        }}
        onDragLeave={(e) => {
          if (e.currentTarget === e.target) setIsFileDragging(false);
        }}
        onDrop={handleContainerDrop}
      >
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="photo" size={22} /> Фото: {product.name}
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={14} />
          </button>
        </div>

        <p style={{ color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
          Перетаскивайте карточки для смены порядка (первое фото — главное). Вы также можете
          загрузить файлы с компьютера или вставить прямую ссылку.
        </p>

        {photos.length === 0 ? (
          <div
            className={`drop-zone ${isFileDragging ? 'dragging' : ''}`}
            style={{ padding: '2rem', marginBottom: '1rem' }}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="drop-zone-icon">
              <Icon name="photo" size={40} />
            </div>
            <div className="drop-zone-text">
              Фотографий пока нет. <strong>Нажмите, чтобы выбрать файлы</strong>, перетащите их сюда
              или добавьте по ссылке ниже.
              <br />
              <small>JPG, PNG, WEBP до 10 МБ</small>
            </div>
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
                  src={resolveThumbUrl(url)}
                  alt={`Фото ${idx + 1}`}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  onError={(e) => handleImgError(e, url)}
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

        {/* Скрытый input для загрузки файлов с компьютера */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => handleUploadFiles(e.target.files)}
        />

        {/* Строка добавления по ссылке + кнопка выбора файла */}
        <div className="photos-add-row" style={{ flexWrap: 'wrap' }}>
          <input
            className="form-input"
            style={{ flex: '1 1 260px' }}
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            placeholder="https://example.com/photo.jpg"
          />
          <Button
            variant="secondary"
            onClick={handleAdd}
            disabled={!newUrl.trim().startsWith('http')}
          >
            <Icon name="plus" size={14} /> По ссылке
          </Button>
          <Button
            variant="secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            loading={uploading}
            title="Загрузить изображения с компьютера (JPG, PNG, WEBP)"
          >
            <Icon name="import" size={14} /> Загрузить файлы
          </Button>
        </div>

        <div className="modal-actions">
          <Button
            variant="outline"
            onClick={handleDownload}
            disabled={downloading || photos.length === 0}
            loading={downloading}
            title="Скачать внешние фото на сервер, чтобы они не зависели от чужих сайтов"
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
