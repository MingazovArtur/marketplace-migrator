import React, { useState, useEffect, useRef } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';

const API_URL = 'http://localhost:8000/api';

const authHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const HINTS = {
  ozon: 'Тест: test:test · Реальный API: CLIENT_ID:API_KEY',
  wildberries: 'Тест: mock_wb_key (демо-режим)',
  yandex: 'Тест: test:test · API: campaign_id:oauth_token · или ссылка на YML-фид',
  magnit: 'Магнит Маркет: только XLSX из личного кабинета, лист «SKU». Цен в файле нет — задайте их после импорта через «Редактировать».',
};

const ImportModal = ({ isOpen, onClose, onImport, onFileImport, loading }) => {
  const [selectedPlatform, setSelectedPlatform] = useState('ozon');
  const [importMethod, setImportMethod] = useState('file');
  const [authKey, setAuthKey] = useState('');
  const [keyError, setKeyError] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [upsert, setUpsert] = useState(false);
  const [isImported, setIsImported] = useState(false);
  const fileInputRef = useRef(null);

  const platform = PLATFORMS.find((p) => p.id === selectedPlatform) || PLATFORMS[0];
  const availableMethods = platform.importMethods || ['key', 'file'];

  useEffect(() => {
    if (!availableMethods.includes(importMethod)) setImportMethod(availableMethods[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPlatform]);

  useEffect(() => {
    if (isOpen) {
      setAuthKey(''); setKeyError(''); setSelectedFile(null);
      setPreview(null); setPreviewError(''); setIsDragging(false);
      setUpsert(false); setIsImported(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const changePlatform = (id) => {
    setSelectedPlatform(id);
    setSelectedFile(null); setPreview(null); setPreviewError('');
    setAuthKey(''); setKeyError(''); setIsImported(false);
  };

  const validateKey = (v) => {
    if (!v.trim()) return 'Укажите ключ или ссылку';
    if (v.trim().length < 3) return 'Слишком короткое значение';
    return null;
  };

  const handleKeyImport = () => {
    const err = validateKey(authKey);
    if (err) { setKeyError(err); return; }
    const k = authKey.trim();
    const full = k.includes(':') && k.split(':')[0].toLowerCase() === selectedPlatform
      ? k
      : `${selectedPlatform}:${k}`;
    setIsImported(true);
    onImport(full);
  };

  const downloadTemplate = async () => {
    try {
      const res = await fetch(`${API_URL}/templates/${selectedPlatform}`, { headers: authHeaders() });
      if (!res.ok) throw new Error('шаблон не найден');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `template_${selectedPlatform}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setPreviewError('Не удалось скачать шаблон: ' + e.message);
    }
  };

  const loadPreview = async (file) => {
    setSelectedFile(file); setPreview(null); setPreviewError('');
    setPreviewLoading(true); setIsImported(false);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('platform', selectedPlatform);
      const res = await fetch(`${API_URL}/import/preview`, {
        method: 'POST',
        headers: authHeaders(),
        body: fd,
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || 'Не удалось прочитать файл');
      setPreview(data.preview);
    } catch (e) {
      setPreviewError(e.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const pickFile = (file) => {
    if (!file) return;
    if (!/\.(xlsx|csv)$/i.test(file.name)) {
      setPreviewError('Поддерживаются только файлы .xlsx и .csv');
      return;
    }
    loadPreview(file);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    pickFile(e.dataTransfer.files?.[0]);
  };

  const confirmFileImport = () => {
    if (!selectedFile || isImported) return;
    setIsImported(true);
    onFileImport(selectedPlatform, selectedFile, upsert ? 'upsert' : 'create');
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="import" size={22} /> Импорт товаров
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        {/* 1. Площадка */}
        <label className="form-label">1. Площадка-источник:</label>
        <div className="platform-selector">
          {PLATFORMS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`}
              onClick={() => changePlatform(p.id)}
            >
              <div
                className="platform-logo"
                style={{
                  backgroundColor: selectedPlatform === p.id ? p.color : 'var(--bg-tertiary)',
                  color: selectedPlatform === p.id ? 'white' : 'var(--text-muted)',
                }}
              >
                {p.logoText}
              </div>
              <span>{p.name}</span>
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
          <Button variant="outline" onClick={downloadTemplate}>
            <Icon name="template" size={16} /> Скачать шаблон
          </Button>
        </div>

        {/* 2. Способ */}
        <label className="form-label">2. Способ импорта:</label>
        {availableMethods.length > 1 ? (
          <div className="import-method-toggle">
            <button
              type="button"
              className={`toggle-btn ${importMethod === 'key' ? 'active' : ''}`}
              onClick={() => setImportMethod('key')}
            >
              <Icon name="key" size={16} /> API ключ / YML
            </button>
            <button
              type="button"
              className={`toggle-btn ${importMethod === 'file' ? 'active' : ''}`}
              onClick={() => setImportMethod('file')}
            >
              <Icon name="file" size={16} /> Excel / CSV
            </button>
          </div>
        ) : (
          <div className="modal-hint-box">
            <span className="hint-icon"><Icon name="file" size={18} /></span>
            <p>Для «{platform.name}» доступен только импорт из файла XLSX.</p>
          </div>
        )}

        {importMethod === 'key' ? (
          <>
            <div className="modal-hint-box">
              <span className="hint-icon"><Icon name="info" size={18} /></span>
              <p>{HINTS[selectedPlatform]}</p>
            </div>
            <label className="form-label">Ключ или ссылка</label>
            <input
              className={`form-input ${keyError ? 'input-error' : ''}`}
              type="text"
              value={authKey}
              onChange={(e) => { setAuthKey(e.target.value); setKeyError(''); }}
              placeholder={selectedPlatform === 'yandex' ? 'test:test или https://.../yml.xml' : 'test:test'}
            />
            {keyError && <div className="input-error-message">{keyError}</div>}
            <div className="modal-actions">
              <Button variant="outline" onClick={onClose}>Отмена</Button>
              <Button onClick={handleKeyImport} disabled={loading || isImported} loading={loading || isImported}>
                {isImported ? <Icon name="check" size={16} /> : <Icon name="import" size={16} />}
                {isImported ? 'Импортировано' : 'Импортировать'}
              </Button>
            </div>
          </>
        ) : (
          <>
            {!preview && !previewLoading && (
              <>
                <div className="modal-hint-box">
                  <span className="hint-icon"><Icon name="info" size={18} /></span>
                  <p>{HINTS[selectedPlatform]}</p>
                </div>

                <div
                  className={`drop-zone ${isDragging ? 'dragging' : ''}`}
                  onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
                  onDrop={onDrop}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <div className="drop-zone-icon"><Icon name="file" size={44} /></div>
                  <div className="drop-zone-text">
                    {selectedFile ? (
                      <>
                        <strong>{selectedFile.name}</strong>
                        <br />
                        <small>{(selectedFile.size / 1024).toFixed(1)} KB</small>
                      </>
                    ) : (
                      <>
                        Перетащите файл сюда или <strong>нажмите для выбора</strong>
                        <br />
                        <small>.xlsx / .csv</small>
                      </>
                    )}
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".xlsx,.csv"
                    style={{ display: 'none' }}
                    onChange={(e) => pickFile(e.target.files?.[0])}
                  />
                </div>

                {previewError && (
                  <div className="alert alert-error" style={{ marginTop: '1rem' }}>
                    <div>
                      {previewError}
                      <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                        <Button variant="outline" onClick={() => setPreviewError('')}>
                          Попробовать другой файл
                        </Button>
                        {selectedFile && (
                          <Button onClick={confirmFileImport} disabled={loading || isImported}>
                            <Icon name="import" size={16} /> Импорт без предпросмотра
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}

            {previewLoading && (
              <div className="progress-status">⏳ Читаем файл и строим предпросмотр...</div>
            )}

            {preview && (
              <div className="preview-section">
                <div className="preview-summary">
                  <span>Строк в файле: <b>{preview.total_estimated}</b></span>
                  <span>Будет импортировано: <b>{preview.valid_estimated}</b></span>
                  <span>Ошибок: <b>{preview.errors?.length || 0}</b></span>
                </div>

                {preview.warnings?.length > 0 && (
                  <div className="modal-hint-box">
                    <span className="hint-icon"><Icon name="alert" size={18} /></span>
                    <p>{preview.warnings.map((w) => w.message).join(' ')}</p>
                  </div>
                )}

                <div className="preview-table-wrap">
                  <table className="preview-table">
                    <thead>
                      <tr>{(preview.columns || []).map((c) => (<th key={c}>{c}</th>))}</tr>
                    </thead>
                    <tbody>
                      {(preview.preview || []).map((row, i) => (
                        <tr key={i}>
                          {(preview.columns || []).map((c) => (
                            <td key={c} title={String(row[c] ?? '')}>
                              {String(row[c] ?? '').slice(0, 60)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {preview.errors?.length > 0 && (
                  <div className="preview-errors">
                    <h4><Icon name="alert" size={16} /> Ошибки в файле:</h4>
                    <ul>
                      {preview.errors.slice(0, 5).map((er, i) => (
                        <li key={i}>Строка {er.row}: {er.error}</li>
                      ))}
                      {preview.errors.length > 5 && <li>…и ещё {preview.errors.length - 5}</li>}
                    </ul>
                  </div>
                )}

                <label className="bulk-check" style={{ margin: '0.75rem 0' }}>
                  <input type="checkbox" checked={upsert} onChange={(e) => setUpsert(e.target.checked)} />
                  Обновлять существующие товары по артикулу (upsert)
                </label>

                <div className="modal-actions">
                  <Button
                    variant="outline"
                    onClick={() => { setPreview(null); setSelectedFile(null); setIsImported(false); }}
                  >
                    <Icon name="chevron-left" size={16} /> Другой файл
                  </Button>
                  <Button
                    onClick={confirmFileImport}
                    disabled={loading || isImported || preview.valid_estimated === 0}
                    loading={loading || isImported}
                  >
                    {isImported
                      ? (<><Icon name="check" size={16} /> Импортировано</>)
                      : (<><Icon name="import" size={16} /> Импортировать {preview.valid_estimated}</>)}
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default ImportModal;