import React, { useState, useEffect, useCallback } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { api } from '../../api';

const STATUS_OPTIONS = [
  { value: 'success', label: 'Только успешные' },
  { value: 'pending', label: 'Ожидающие' },
  { value: 'all', label: 'Все' },
];

const ExportModal = ({ isOpen, onClose, onExport, loading }) => {
  const [platform, setPlatform] = useState('ozon');
  const [status, setStatus] = useState('success');
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [downloaded, setDownloaded] = useState(false); // ✅ защита от повторных скачиваний

  const loadPreview = useCallback(async () => {
    setPreviewLoading(true);
    setPreviewError('');
    setPreview(null);
    try {
      const data = await api.exportPreview(platform, status);
      setPreview(data);
    } catch (e) {
      setPreviewError(e.message);
    } finally {
      setPreviewLoading(false);
    }
  }, [platform, status]);

  useEffect(() => {
    if (isOpen) {
      setDownloaded(false);
      loadPreview();
    }
  }, [isOpen, loadPreview]);

  // Сменили площадку/статус — файл будет другой, разрешаем скачивание снова
  useEffect(() => {
    setDownloaded(false);
  }, [platform, status]);

  if (!isOpen) return null;

  const v = preview?.validation;
  const downloadable = v ? v.ready + v.with_warnings : 0;

  const handleDownload = () => {
    if (downloaded || loading) return;   // ✅ повторный клик игнорируется
    setDownloaded(true);
    onExport(platform, status);
  };

  const handleTemplate = () => {
    api.exportTemplate(platform).catch((e) => setPreviewError(e.message));
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="export" size={22} /> Выгрузка для площадки
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        {/* Параметры */}
        <div className="export-controls">
          <div>
            <label className="form-label">Площадка:</label>
            <select className="form-input" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              {PLATFORMS.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
            </select>
          </div>
          <div>
            <label className="form-label">Статус товаров:</label>
            <select className="form-input" value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUS_OPTIONS.map((s) => (<option key={s.value} value={s.value}>{s.label}</option>))}
            </select>
          </div>
          <div className="export-controls-btn">
            <Button variant="outline" onClick={handleTemplate}>
              <Icon name="template" size={16} /> Шаблон
            </Button>
          </div>
        </div>

        {/* Предпросмотр */}
        {previewLoading && <div className="progress-status">⏳ Готовим предпросмотр...</div>}
        {previewError && <div className="alert alert-error"><div>{previewError}</div></div>}

        {v && v.total === 0 && (
          <div className="empty-state" style={{ padding: '1.5rem' }}>
            <div className="empty-state-icon">📭</div>
            <p className="empty-state-text">Нет товаров с выбранным статусом.</p>
          </div>
        )}

        {v && v.total > 0 && (
          <>
            <div className="export-validation">
              <div className="validation-card ready">
                <div className="validation-num">{v.ready}</div>
                <div>готово к выгрузке</div>
              </div>
              <div className="validation-card warn">
                <div className="validation-num">{v.with_warnings}</div>
                <div>с предупреждениями</div>
              </div>
              <div className="validation-card err">
                <div className="validation-num">{v.with_errors}</div>
                <div>с ошибками (будут пропущены)</div>
              </div>
            </div>

            {v.issues && v.issues.length > 0 && (
              <div className="preview-errors">
                <h4><Icon name="alert" size={16} /> Проблемные товары:</h4>
                <ul>
                  {v.issues.slice(0, 8).map((it) => (
                    <li key={it.product_id}>
                      #{it.product_id} {it.name}: {it.issues.map((i) => i.message).join('; ')}
                    </li>
                  ))}
                  {v.issues.length > 8 && <li>…и ещё {v.issues.length - 8}</li>}
                </ul>
              </div>
            )}

            {preview.rows && preview.rows.length > 0 && (
              <div className="preview-table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>{preview.columns.map((c) => (<th key={c}>{c}</th>))}</tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i}>
                        {preview.columns.map((c) => (
                          <td key={c} title={String(row[c] ?? '')}>
                            {String(row[c] ?? '').slice(0, 50)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* Действия */}
        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button
            onClick={handleDownload}
            disabled={downloaded || loading || downloadable === 0}
            title={downloaded ? 'Файл уже скачан. Закройте окно или измените параметры.' : ''}
          >
            {downloaded
              ? (<><Icon name="check" size={16} /> Файл скачан</>)
              : (<><Icon name="export" size={16} /> Скачать файл ({downloadable})</>)}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ExportModal;