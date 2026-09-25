import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { api } from '../../api';

const STATUS_OPTIONS = [
  { value: 'success', label: 'Только успешные' },
  { value: 'pending', label: 'Ожидающие' },
  { value: 'all',     label: 'Все' },
];

const OZON_TEMPLATE_REQUIRED = [
  { field: 'article',      label: 'Артикул' },
  { field: 'price',        label: 'Предельная цена без акций, руб.' },
  { field: 'vat_rate',     label: 'НДС, %' },
  { field: 'okpd_code',    label: 'ТН ВЭД коды ЕАЭС' },
  { field: 'dimensions',   label: 'Вес в упаковке, г' },
  { field: 'dimensions',   label: 'Ширина упаковки, мм' },
  { field: 'dimensions',   label: 'Высота упаковки, мм' },
  { field: 'dimensions',   label: 'Длина упаковки, мм' },
  { field: 'main_photo',   label: 'Ссылка на главное фото' },
  { field: 'attr:brand',   label: 'Бренд' },
  { field: 'attr:model',   label: 'Название модели (для объединения в одну карточку)' },
  { field: 'attr:type',    label: 'Тип' },
  { field: 'attr:marking', label: 'Нужен код маркировки' },
];

const CANON_SYNONYMS = {
  brand:   ['бренд', 'брендводеждеиобуви', 'брендодеждыиобуви'],
  model:   ['названиемодели', 'названиемоделидляобъединенияводнукарточку',
            'объединитьнаоднойкарточке', 'объединитьводнукарточку', 'модель'],
  type:    ['тип'],
  marking: ['нуженкодмаркировки', 'кодмаркировки', 'маркировка'],
};
const normName = (s) => (s || '').toLowerCase().replace(/[^a-zа-я0-9]/g, '');
const canonFieldFor = (field) => {
  if (!field || !field.startsWith('attr:')) return field;
  const n = normName(field.slice(5));
  for (const [canon, syns] of Object.entries(CANON_SYNONYMS)) {
    if (syns.map(normName).includes(n)) return `attr:${canon}`;
  }
  return field;
};

const ExportModal = ({ isOpen, onClose, onExport, loading }) => {
  const [platform, setPlatform] = useState('ozon');
  const [status, setStatus] = useState('success');
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [downloaded, setDownloaded] = useState(false);
  const [validation, setValidation] = useState(null);

  // ---- Эталонные шаблоны ----
  const [specNames, setSpecNames] = useState([]);
  const [tplCategory, setTplCategory] = useState('');
  const [tplFile, setTplFile] = useState(null);
  const [tplUploading, setTplUploading] = useState(false);
  const [tplList, setTplList] = useState([]);
  const [tplMessage, setTplMessage] = useState('');

  const loadTplList = useCallback(async () => {
    const d = await api.listOzonTemplates();
    setTplList(d.templates || []);
  }, []);

  const loadPreview = useCallback(async () => {
    setPreviewLoading(true);
    setPreviewError('');
    setPreview(null);
    setValidation(null);
    try {
      const [pv, vv] = await Promise.all([
        api.exportPreview(platform, status),
        api.validateExport(platform, status).catch(() => null),
      ]);
      setPreview(pv);
      setValidation(vv);
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
      loadTplList();
      if (platform === 'ozon') {
        api.getSpecNames('ozon').then(setSpecNames).catch(() => setSpecNames([]));
      }
    }
  }, [isOpen, loadPreview, loadTplList, platform]);

  useEffect(() => { setDownloaded(false); }, [platform, status]);

  if (!isOpen) return null;

  const v = validation || preview?.validation || {};
  const total = v.total ?? 0;
  const withErrors = v.products_with_errors ?? 0;
  const withWarnings = Math.max(0, (v.products_with_warnings ?? 0) - withErrors);
  const downloadable = total - withErrors;

  const errorCountByCanon = useMemo(() => {
    const counts = {};
    (v.issues || []).forEach((it) =>
      (it.issues || []).forEach((i) => {
        if (i.severity === 'error') {
          const f = canonFieldFor(i.field);
          counts[f] = (counts[f] || 0) + 1;
        }
      })
    );
    return counts;
  }, [v]);

  const checklist = useMemo(
    () => OZON_TEMPLATE_REQUIRED.map((f) => ({ ...f, count: errorCountByCanon[f.field] || 0 })),
    [errorCountByCanon]
  );
  const missingAny = checklist.some((f) => f.count > 0);

  const handleDownload = () => {
    if (downloaded || loading) return;
    setDownloaded(true);
    onExport(platform, status);
  };

  const handleTemplate = () => {
    api.exportTemplate(platform).catch((e) => setPreviewError(e.message));
  };

  const handleUploadTpl = async () => {
    if (!tplCategory.trim() || !tplFile) return;
    setTplUploading(true);
    setTplMessage('');
    setPreviewError('');
    try {
      const r = await api.uploadOzonTemplate(tplCategory.trim(), tplFile);
      setTplMessage(`✅ ${r.message || 'Эталон сохранён'}`);
      setTplFile(null);
      await loadTplList();
      loadPreview();
    } catch (e) {
      setPreviewError(e.message);
    } finally {
      setTplUploading(false);
    }
  };

  const handleDeleteTpl = async (cat) => {
    try {
      await api.deleteOzonTemplate(cat);
      setTplMessage(`🗑 Эталон для «${cat}» удалён — выгрузка вернётся к генерации из спека.`);
      await loadTplList();
    } catch (e) {
      setPreviewError(e.message);
    }
  };

  const groupIssues = (issues) => ({
    errors: issues.filter((i) => i.severity === 'error'),
    warnings: issues.filter((i) => i.severity === 'warning'),
  });

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

        {/* ✅ Эталонные шаблоны Ozon */}
        {platform === 'ozon' && (
          <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
            <h4 style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Icon name="template" size={16} /> Эталонный шаблон Ozon для категории
            </h4>
            <p className="form-hint" style={{ marginTop: 0, marginBottom: '0.6rem' }}>
              Скачайте XLSX-шаблон в кабинете Ozon для нужной категории и загрузите его здесь.
              Система возьмёт его формат (колонки, порядок, цвета, выпадающие списки, доп. листы)
              как основу и подставит только строки товаров — файл будет идентичен шаблону площадки.
            </p>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
              <input
                className="form-input"
                list="tpl-categories"
                placeholder="Одежда / Футболка"
                value={tplCategory}
                onChange={(e) => setTplCategory(e.target.value)}
                style={{ flex: 1, minWidth: 220 }}
              />
              <datalist id="tpl-categories">
                {specNames.map((n) => (<option key={n} value={n} />))}
              </datalist>
              <input
                type="file"
                accept=".xlsx"
                onChange={(e) => setTplFile(e.target.files?.[0] || null)}
              />
              <Button onClick={handleUploadTpl} disabled={!tplCategory.trim() || !tplFile || tplUploading} loading={tplUploading}>
                Сохранить эталон
              </Button>
            </div>
            {tplList.length > 0 && (
              <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Загружены эталоны:{' '}
                {tplList.map((cat) => (
                  <span key={cat} style={{ marginRight: '0.6rem', whiteSpace: 'nowrap' }}>
                    ✅ {cat}{' '}
                    <button
                      type="button"
                      title="Удалить эталон"
                      onClick={() => handleDeleteTpl(cat)}
                      style={{ background: 'none', border: 'none', color: 'var(--danger, #ef4444)', cursor: 'pointer', padding: 0 }}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}
            {tplMessage && (
              <div className="alert alert-success" style={{ marginTop: '0.5rem', marginBottom: 0 }}>
                <div>{tplMessage}</div>
              </div>
            )}
          </div>
        )}

        {/* Чек-лист 13 канонических полей */}
        {platform === 'ozon' && (
          <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
            <h4 style={{ margin: '0 0 0.6rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Icon name="check" size={16} /> Обязательные поля XLS-шаблона Ozon (13 колонок)
            </h4>
            <p className="form-hint" style={{ marginTop: 0, marginBottom: '0.6rem' }}>
              Только отсутствие этих полей блокирует экспорт. Прочие атрибуты спека — предупреждения.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.25rem 1rem', fontSize: '0.85rem' }}>
              {checklist.map((f, idx) => (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  {f.count === 0 ? (
                    <span style={{ color: 'var(--success, #22c55e)' }}>✅</span>
                  ) : (
                    <span style={{ color: 'var(--danger, #ef4444)', fontWeight: 600 }}>❌ {f.count}</span>
                  )}
                  <span style={{ color: f.count === 0 ? 'var(--text-secondary)' : 'var(--text-primary)' }}>
                    {f.label}
                  </span>
                </div>
              ))}
            </div>
            {!missingAny && total > 0 && (
              <div className="alert alert-success" style={{ marginTop: '0.6rem', marginBottom: 0 }}>
                <div>✅ Все обязательные поля заполнены. Файл пройдёт валидацию Ozon.</div>
              </div>
            )}
            {missingAny && (
              <div className="alert alert-error" style={{ marginTop: '0.6rem', marginBottom: 0 }}>
                <div>❌ Заполните поля со значком ❌ через «Логистику», «Характеристики» или «Фото» и повторите экспорт.</div>
              </div>
            )}
          </div>
        )}

        {/* Сводка готовности */}
        {total > 0 && (
          <div className="export-validation">
            <div className="validation-card ready">
              <div className="validation-num">{downloadable}</div>
              <div>готово к выгрузке</div>
            </div>
            <div className="validation-card warn">
              <div className="validation-num">{withWarnings}</div>
              <div>с предупреждениями (пройдут)</div>
            </div>
            <div className="validation-card err">
              <div className="validation-num">{withErrors}</div>
              <div>с ошибками (будут пропущены)</div>
            </div>
          </div>
        )}

        {previewLoading && (
          <div className="progress-status" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
            <div className="spinner spinner-dark" /> Готовим предпросмотр...
          </div>
        )}
        {previewError && <div className="alert alert-error"><div>{previewError}</div></div>}

        {total === 0 && !previewLoading && (
          <div className="empty-state" style={{ padding: '1.5rem' }}>
            <div className="empty-state-icon" style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-muted)' }}>
              <Icon name="products" size={48} />
            </div>
            <p className="empty-state-text">Нет товаров с выбранным статусом.</p>
          </div>
        )}

        {total > 0 && v.issues && v.issues.length > 0 && (
          <div className="preview-errors">
            <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Icon name="warning" size={16} /> Проблемные товары ({v.issues.length}):
            </h4>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0.5rem 0 0' }}>
              {v.issues.slice(0, 8).map((it) => {
                const { errors, warnings } = groupIssues(it.issues);
                return (
                  <li
                    key={it.product_id}
                    style={{
                      padding: '0.5rem 0.6rem', marginBottom: '0.4rem',
                      background: 'var(--bg-secondary)', borderRadius: '6px',
                      borderLeft: errors.length ? '3px solid var(--danger, #ef4444)' : '3px solid var(--warning, #f59e0b)',
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
                      #{it.product_id} {it.product_name}
                    </div>
                    {errors.length > 0 && (
                      <div style={{ color: 'var(--danger, #ef4444)', fontSize: '0.85rem' }}>
                        {errors.map((i, idx) => (
                          <div key={idx} style={{ marginBottom: idx < errors.length - 1 ? '0.15rem' : 0 }}>
                            ❌ <strong>{i.field}</strong>: {i.message}
                          </div>
                        ))}
                      </div>
                    )}
                    {warnings.length > 0 && (
                      <div style={{ color: 'var(--warning, #f59e0b)', fontSize: '0.85rem', marginTop: errors.length ? '0.25rem' : 0 }}>
                        ⚠️ {warnings.slice(0, 3).map((i) => i.message).join('; ')}
                        {warnings.length > 3 && <>; …и ещё {warnings.length - 3}</>}
                      </div>
                    )}
                  </li>
                );
              })}
              {v.issues.length > 8 && (
                <li style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  …и ещё {v.issues.length - 8} проблемных товаров
                </li>
              )}
            </ul>
          </div>
        )}

        {preview?.rows && preview.rows.length > 0 && (
          <div className="preview-table-wrap" style={{ marginTop: '0.75rem' }}>
            <table className="preview-table">
              <thead>
                <tr>{preview.columns.map((c) => (<th key={c}>{c}</th>))}</tr>
              </thead>
              <tbody>
                {preview.rows.map((row, i) => (
                  <tr key={i}>
                    {preview.columns.map((c) => (
                      <td key={c} title={String(row[c] ?? '')}>{String(row[c] ?? '').slice(0, 50)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button
            onClick={handleDownload}
            disabled={downloaded || loading || downloadable === 0}
            title={
              downloaded ? 'Файл уже скачан. Закройте окно или измените параметры.'
                : downloadable === 0 ? `Все ${total} товаров имеют ошибки — исправьте поля со значком ❌`
                : `Скачать XLSX с ${downloadable} товарами`
            }
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