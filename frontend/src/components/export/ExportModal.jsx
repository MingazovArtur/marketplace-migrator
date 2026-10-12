import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { api } from '../../api';

const STATUS_OPTIONS = [
  { value: 'success', label: 'Только успешные' },
  { value: 'pending', label: 'Ожидающие' },
  { value: 'all', label: 'Все' },
];

// Канонические 13 полей XLS-шаблона Ozon (эталон 23–25.09.2026)
const OZON_TEMPLATE_REQUIRED = [
  { field: 'article', label: 'Артикул' },
  { field: 'price', label: 'Предельная цена без акций, руб.' },
  { field: 'vat_rate', label: 'НДС, %' },
  { field: 'okpd_code', label: 'ТН ВЭД коды ЕАЭС' },
  { field: 'dimensions', label: 'Вес в упаковке, г' },
  { field: 'dimensions', label: 'Ширина упаковки, мм' },
  { field: 'dimensions', label: 'Высота упаковки, мм' },
  { field: 'dimensions', label: 'Длина упаковки, мм' },
  { field: 'main_photo', label: 'Ссылка на главное фото' },
  { field: 'attr:brand', label: 'Бренд' },
  { field: 'attr:model', label: 'Название модели (для объединения в одну карточку)' },
  { field: 'attr:type', label: 'Тип' },
  { field: 'attr:marking', label: 'Нужен код маркировки' },
];

const CANON_SYNONYMS = {
  brand: ['бренд', 'брендводеждеиобуви', 'брендодеждыиобуви'],
  model: [
    'названиемодели',
    'названиемоделидляобъединенияводнукарточку',
    'объединитьнаоднойкарточке',
    'объединитьводнукарточку',
    'модель',
  ],
  type: ['тип'],
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

const ExportModal = ({ isOpen, onClose, onExport, loading, onOpenTemplates }) => {
  // ✅ 1. ВСЕ STATE В НАЧАЛЕ
  const [platform, setPlatform] = useState('ozon');
  const [status, setStatus] = useState('success');
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [downloaded, setDownloaded] = useState(false);
  const [validation, setValidation] = useState(null);
  const [categoryCounts, setCategoryCounts] = useState({});
  const [tplSet, setTplSet] = useState(new Set());

  // ✅ 2. ВСЕ CALLBACK В НАЧАЛЕ
  const loadPreview = useCallback(async () => {
    setPreviewLoading(true);
    setPreviewError('');
    setPreview(null);
    setValidation(null);
    try {
      const [pv, vv, prods, tpls] = await Promise.all([
        api.exportPreview(platform, status),
        api.validateExport(platform, status).catch(() => null),
        api
          .getProducts({ status: status === 'all' ? undefined : status, limit: 10000 })
          .catch(() => ({ products: [] })),
        platform === 'ozon'
          ? api.listOzonTemplates().catch(() => ({ templates: [] }))
          : { templates: [] },
      ]);
      setPreview(pv);
      setValidation(vv);
      setTplSet(new Set(tpls.templates || []));

      const counts = {};
      (prods.products || []).forEach((p) => {
        const c = p.mapped_category || p.category || 'Без категории';
        counts[c] = (counts[c] || 0) + 1;
      });
      setCategoryCounts(counts);
    } catch (e) {
      setPreviewError(e.message);
    } finally {
      setPreviewLoading(false);
    }
  }, [platform, status]);

  const handleDownload = useCallback(() => {
    if (downloaded || loading) return;
    setDownloaded(true);
    onExport(platform, status);
  }, [downloaded, loading, onExport, platform, status]);

  const handleTemplate = useCallback(() => {
    api.exportTemplate(platform).catch((e) => setPreviewError(e.message));
  }, [platform]);

  const groupIssues = useCallback(
    (issues) => ({
      errors: issues.filter((i) => i.severity === 'error'),
      warnings: issues.filter((i) => i.severity === 'warning'),
    }),
    []
  );

  // ✅ 3. ВСЕ EFFECT В НАЧАЛЕ
  useEffect(() => {
    if (isOpen) {
      setDownloaded(false);
      loadPreview();
    }
  }, [isOpen, loadPreview]);

  useEffect(() => {
    setDownloaded(false);
  }, [platform, status]);

  // ✅ 4. ВСЕ MEMO И ВЫЧИСЛЕНИЯ ДО РАННЕГО ВОЗВРАТА
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

  const missingAny = useMemo(() => checklist.some((f) => f.count > 0), [checklist]);

  const missingTemplates = useMemo(
    () =>
      Object.keys(categoryCounts)
        .filter((c) => platform === 'ozon' && !tplSet.has(c))
        .sort((a, b) => categoryCounts[b] - categoryCounts[a]),
    [categoryCounts, platform, tplSet]
  );

  // ✅ 5. ТЕПЕРЬ БЕЗОПАСНЫЙ РАННИЙ ВОЗВРАТ
  if (!isOpen) return null;

  // ✅ 6. РЕНДЕР
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
            <select
              className="form-input"
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
            >
              {PLATFORMS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">Статус товаров:</label>
            <select
              className="form-input"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="export-controls-btn">
            <Button variant="outline" onClick={handleTemplate}>
              <Icon name="template" size={16} /> Шаблон
            </Button>
          </div>
        </div>

        {/* ✅ Статус эталонов по категориям текущей выгрузки */}
        {platform === 'ozon' && Object.keys(categoryCounts).length > 0 && (
          <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
            <h4
              style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <Icon name="template" size={16} /> Эталонные шаблоны категорий выгрузки
            </h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
              {Object.entries(categoryCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([cat, n]) => (
                  <span
                    key={cat}
                    title={
                      tplSet.has(cat)
                        ? `Эталон загружен — файл соберётся на его основе (${n} тов.)`
                        : `Эталона нет — файл сгенерируется из спека (${n} тов.)`
                    }
                    style={{
                      padding: '0.2rem 0.6rem',
                      borderRadius: 999,
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      background: tplSet.has(cat) ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                      color: tplSet.has(cat) ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)',
                      border: `1px solid ${tplSet.has(cat) ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)'}`,
                    }}
                  >
                    {tplSet.has(cat) ? '✅' : '❌'} {cat} · {n}
                  </span>
                ))}
            </div>
            {missingTemplates.length > 0 && (
              <div className="alert alert-error" style={{ marginTop: '0.6rem', marginBottom: 0 }}>
                <div>
                  ❌ Нет эталонов для категорий: {missingTemplates.join(', ')}. Выгрузка по ним
                  соберётся из спека и может отличаться от шаблона кабинета Ozon.
                  {onOpenTemplates && (
                    <>
                      {' '}
                      <button
                        type="button"
                        onClick={() => {
                          onClose();
                          onOpenTemplates();
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          cursor: 'pointer',
                          color: 'var(--primary, #3b82f6)',
                          textDecoration: 'underline',
                          fontWeight: 700,
                        }}
                      >
                        Открыть страницу «Шаблоны площадок» →
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
            {missingTemplates.length === 0 && (
              <p className="form-hint" style={{ marginTop: '0.5rem', marginBottom: 0 }}>
                ✅ Все категории выгрузки обеспечены эталонными шаблонами — файлы будут идентичны
                шаблонам Ozon.
              </p>
            )}
          </div>
        )}

        {/* Чек-лист 13 канонических полей */}
        {platform === 'ozon' && (
          <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
            <h4
              style={{ margin: '0 0 0.6rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <Icon name="check" size={16} /> Обязательные поля XLS-шаблона Ozon (13 колонок)
            </h4>
            <p className="form-hint" style={{ marginTop: 0, marginBottom: '0.6rem' }}>
              Только отсутствие этих полей блокирует экспорт. Прочие атрибуты спека —
              предупреждения.
            </p>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: '0.25rem 1rem',
                fontSize: '0.85rem',
              }}
            >
              {checklist.map((f, idx) => (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  {f.count === 0 ? (
                    <span style={{ color: 'var(--success, #22c55e)' }}>✅</span>
                  ) : (
                    <span style={{ color: 'var(--danger, #ef4444)', fontWeight: 600 }}>
                      ❌ {f.count}
                    </span>
                  )}
                  <span
                    style={{
                      color: f.count === 0 ? 'var(--text-secondary)' : 'var(--text-primary)',
                    }}
                  >
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
                <div>
                  ❌ Заполните поля со значком ❌ через «Логистику», «Характеристики», «Фото» или
                  «Дефолты» и повторите экспорт.
                </div>
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
          <div
            className="progress-status"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
            }}
          >
            <div className="spinner spinner-dark" /> Готовим предпросмотр...
          </div>
        )}
        {previewError && (
          <div className="alert alert-error">
            <div>{previewError}</div>
          </div>
        )}

        {total === 0 && !previewLoading && (
          <div className="empty-state" style={{ padding: '1.5rem' }}>
            <div
              className="empty-state-icon"
              style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-muted)' }}
            >
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
                      padding: '0.5rem 0.6rem',
                      marginBottom: '0.4rem',
                      background: 'var(--bg-secondary)',
                      borderRadius: '6px',
                      borderLeft: errors.length
                        ? '3px solid var(--danger, #ef4444)'
                        : '3px solid var(--warning, #f59e0b)',
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
                      #{it.product_id} {it.product_name}
                    </div>
                    {errors.length > 0 && (
                      <div style={{ color: 'var(--danger, #ef4444)', fontSize: '0.85rem' }}>
                        {errors.map((i, idx) => (
                          <div
                            key={idx}
                            style={{ marginBottom: idx < errors.length - 1 ? '0.15rem' : 0 }}
                          >
                            ❌ <strong>{i.field}</strong>: {i.message}
                          </div>
                        ))}
                      </div>
                    )}
                    {warnings.length > 0 && (
                      <div
                        style={{
                          color: 'var(--warning, #f59e0b)',
                          fontSize: '0.85rem',
                          marginTop: errors.length ? '0.25rem' : 0,
                        }}
                      >
                        ⚠️{' '}
                        {warnings
                          .slice(0, 3)
                          .map((i) => i.message)
                          .join('; ')}
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
                <tr>
                  {preview.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
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

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button
            onClick={handleDownload}
            disabled={downloaded || loading || downloadable === 0}
            title={
              downloaded
                ? 'Файл уже скачан. Закройте окно или измените параметры.'
                : downloadable === 0
                  ? `Все ${total} товаров имеют ошибки — исправьте поля со значком ❌`
                  : `Скачать XLSX с ${downloadable} товарами`
            }
          >
            {downloaded ? (
              <>
                <Icon name="check" size={16} /> Файл скачан
              </>
            ) : (
              <>
                <Icon name="export" size={16} /> Скачать файл ({downloadable})
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ExportModal;
