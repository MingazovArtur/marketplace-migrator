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

const UNIVERSAL_NAMES = new Set([
  'универсальный',
  'универсальный (все категории)',
  'общий',
  'все категории',
  'default',
  'all',
]);

const normName = (s) => (s || '').toLowerCase().replace(/[^a-zа-я0-9]/g, '');
const canonFieldFor = (field) => {
  if (!field || !field.startsWith('attr:')) return field;
  const n = normName(field.slice(5));
  for (const [canon, syns] of Object.entries(CANON_SYNONYMS)) {
    if (syns.map(normName).includes(n)) return `attr:${canon}`;
  }
  return field;
};

// Человекочитаемые подписи полей дефолтов (кнопка «Заполнить пропуски»)
const DEFAULTS_FIELD_LABELS = {
  vat_rate: 'НДС, %',
  okpd_code: 'ТН ВЭД коды ЕАЭС',
  package_weight_grams: 'Вес в упаковке, г',
  package_width_mm: 'Ширина упаковки, мм',
  package_height_mm: 'Высота упаковки, мм',
  package_length_mm: 'Длина упаковки, мм',
  price: 'Цена',
  brand: 'Бренд',
  marking: 'Код маркировки',
};
const formatDefaultsResult = (res) => {
  if (!res || !res.updated)
    return 'Нечего дозаполнять: пустых полей не найдено либо дефолты не заданы (кнопка «Дефолты» на странице «Товары»).';
  const parts = Object.entries(res.fields || {}).map(
    ([k, n]) => `${DEFAULTS_FIELD_LABELS[k] || k}: ${n}`
  );
  return (
    `Дозаполнено ${res.updated} из ${res.total} товаров` +
    (parts.length ? ` (${parts.join(', ')})` : '')
  );
};

const ExportModal = ({ isOpen, onClose, onExport, loading, onOpenTemplates, selectedIds = [] }) => {
  const [platform, setPlatform] = useState('ozon');
  const [status, setStatus] = useState('success');
  const [onlySelected, setOnlySelected] = useState(selectedIds.length > 0);
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [downloaded, setDownloaded] = useState(false);
  const [validation, setValidation] = useState(null);
  const [categoryCounts, setCategoryCounts] = useState({});
  const [tplSet, setTplSet] = useState(new Set());
  // ✅ Превалидация: кнопка «Заполнить пропуски дефолтами»
  const [defaultsLoading, setDefaultsLoading] = useState(false);
  const [defaultsResult, setDefaultsResult] = useState(null);
  // ✅ v4: инкрементальный экспорт — только изменённые с последней выгрузки
  const [changedSince, setChangedSince] = useState(false);

  const activeIds = useMemo(
    () => (onlySelected && selectedIds.length > 0 ? selectedIds : null),
    [onlySelected, selectedIds]
  );

  const loadPreview = useCallback(async () => {
    setPreviewLoading(true);
    setPreviewError('');
    setPreview(null);
    setValidation(null);
    setDefaultsResult(null);
    try {
      // ✅ О3: счётчики категорий — лёгкий GROUP BY вместо выгрузки 10 000
      // товаров с атрибутами и вариациями (было: api.getProducts({limit: 10000}))
      const [pv, vv, countsRes, tpls] = await Promise.all([
        api.exportPreview(platform, status, activeIds, changedSince),
        api.validateExport(platform, status, activeIds, changedSince).catch(() => null),
        api
          .getCategoryCounts({
            status: status === 'all' ? undefined : status,
            productIds: activeIds || undefined,
          })
          .catch(() => ({})),
        api.listOzonTemplates(platform).catch(() => ({ templates: [] })),
      ]);
      setPreview(pv);
      setValidation(vv);
      setTplSet(new Set(tpls.templates || []));
      setCategoryCounts(countsRes);
    } catch (e) {
      setPreviewError(e.message);
    } finally {
      setPreviewLoading(false);
    }
  }, [platform, status, activeIds, changedSince]);

  const handleDownload = useCallback(() => {
    if (downloaded || loading) return;
    setDownloaded(true);
    onExport(platform, status, activeIds, changedSince);
  }, [downloaded, loading, onExport, platform, status, activeIds, changedSince]);

  const handleTemplate = useCallback(() => {
    api.exportTemplate(platform).catch((e) => setPreviewError(e.message));
  }, [platform]);

  /* ✅ Превалидация: дозаполнить пустые поля дефолтами прямо из окна выгрузки.
   * Бэкенд заполняет ТОЛЬКО пустые/нулевые поля (цена, НДС, ТН ВЭД, габариты),
   * заполненные значения не перезаписываются. После — перезагружаем проверку. */
  const handleApplyDefaults = useCallback(async () => {
    setDefaultsLoading(true);
    setPreviewError('');
    try {
      const payload = activeIds ? { product_ids: activeIds } : { status };
      const res = await api.applyDefaults(payload);
      setDefaultsResult(res);
      await loadPreview();
    } catch (e) {
      setPreviewError('Не удалось заполнить пропуски: ' + e.message);
    } finally {
      setDefaultsLoading(false);
    }
  }, [activeIds, status, loadPreview]);

  const groupIssues = useCallback(
    (issues) => ({
      errors: issues.filter((i) => (i.severity || i.level) === 'error'),
      warnings: issues.filter((i) => (i.severity || i.level) === 'warning'),
    }),
    []
  );

  useEffect(() => {
    if (isOpen) {
      setOnlySelected(selectedIds.length > 0);
      setDownloaded(false);
      setChangedSince(false);
    }
  }, [isOpen, selectedIds]);

  useEffect(() => {
    if (isOpen) {
      loadPreview();
    }
  }, [isOpen, loadPreview]);

  useEffect(() => {
    setDownloaded(false);
  }, [platform, status, onlySelected, changedSince]);

  const v = validation || preview?.validation || {};
  const total = v.total ?? 0;
  const withErrors = v.products_with_errors ?? v.with_errors ?? 0;
  const withWarnings = Math.max(0, (v.products_with_warnings ?? v.with_warnings ?? 0) - withErrors);
  const downloadable = total - withErrors;

  const errorCountByCanon = useMemo(() => {
    const counts = {};
    (v.issues || []).forEach((it) =>
      (it.issues || []).forEach((i) => {
        if ((i.severity || i.level) === 'error') {
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

  // ✅ Универсальный список блокирующих полей для ЛЮБОЙ площадки (не только Ozon)
  const blockingFields = useMemo(() => {
    const counts = {};
    (v.issues || []).forEach((it) =>
      (it.issues || []).forEach((i) => {
        if ((i.severity || i.level) === 'error') {
          const f = canonFieldFor(i.field);
          counts[f] = (counts[f] || 0) + 1;
        }
      })
    );
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([field, count]) => ({
        field,
        count,
        label: field.startsWith('attr:')
          ? field.slice(5).replace(/_/g, ' ')
          : DEFAULTS_FIELD_LABELS[field] || field,
      }));
  }, [v]);

  const readinessPercent = total > 0 ? Math.round((downloadable / total) * 100) : 0;

  const hasUniversalTemplate = useMemo(
    () => Array.from(tplSet).some((name) => UNIVERSAL_NAMES.has(String(name).trim().toLowerCase())),
    [tplSet]
  );

  const hasTemplateForCategory = useCallback(
    (cat) => {
      if (tplSet.has(cat) || hasUniversalTemplate) return true;
      if (platform !== 'ozon' && tplSet.size > 0) return true;
      return false;
    },
    [tplSet, hasUniversalTemplate, platform]
  );

  const missingTemplates = useMemo(
    () =>
      Object.keys(categoryCounts)
        .filter((c) => !hasTemplateForCategory(c))
        .sort((a, b) => categoryCounts[b] - categoryCounts[a]),
    [categoryCounts, hasTemplateForCategory]
  );

  const currentPlatformMeta = useMemo(
    () => PLATFORMS.find((p) => p.id === platform) || PLATFORMS[0],
    [platform]
  );

  if (!isOpen) return null;

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

        {/* Переключатель: выгружать только отмеченные в таблице товары */}
        {selectedIds.length > 0 && (
          <label
            className="bulk-check"
            style={{
              marginBottom: '0.85rem',
              padding: '0.6rem 0.85rem',
              background: 'rgba(99, 102, 241, 0.1)',
              border: '1px solid rgba(99, 102, 241, 0.35)',
              borderRadius: '8px',
            }}
          >
            <input
              type="checkbox"
              checked={onlySelected}
              onChange={(e) => setOnlySelected(e.target.checked)}
            />
            <span>
              Выгружать{' '}
              <strong>только выбранные в таблице товары ({selectedIds.length} шт.)</strong>
            </span>
          </label>
        )}

        {/* ✅ v4: инкрементальный экспорт — только изменённые с последней выгрузки */}
        {!activeIds && (
          <label
            className="bulk-check"
            style={{
              display: 'flex',
              marginBottom: '0.85rem',
              padding: '0.6rem 0.85rem',
              background: 'rgba(34,197,94,0.08)',
              border: '1px solid rgba(34,197,94,0.35)',
              borderRadius: '8px',
            }}
          >
            <input
              type="checkbox"
              checked={changedSince}
              onChange={(e) => setChangedSince(e.target.checked)}
            />
            <span>
              <strong>Только новые/изменённые с последней выгрузки</strong>
              {v.incremental && !changedSince && (
                <span style={{ color: 'var(--text-secondary)', fontWeight: 'normal' }}>
                  {' '}
                  — сейчас попадёт: новых {v.incremental.new ?? 0}, изменённых{' '}
                  {v.incremental.changed ?? 0} (без изменений: {v.incremental.unchanged ?? 0})
                </span>
              )}
            </span>
          </label>
        )}

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
              disabled={onlySelected && selectedIds.length > 0}
              title={
                onlySelected && selectedIds.length > 0
                  ? 'Выгружаются выбранные чекбоксами товары независимо от статуса'
                  : ''
              }
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

        {/* Статус эталонов выбранной площадки */}
        {Object.keys(categoryCounts).length > 0 && (
          <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
            <h4
              style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <Icon name="template" size={16} /> Эталонные шаблоны выгрузки (
              {currentPlatformMeta.name})
            </h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
              {Object.entries(categoryCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([cat, n]) => {
                  const hasTpl = hasTemplateForCategory(cat);
                  return (
                    <span
                      key={cat}
                      title={
                        hasTpl
                          ? `Эталон загружен — файл соберётся на его основе (${n} тов.)`
                          : `Эталона нет — файл сгенерируется автоматически (${n} тов.)`
                      }
                      style={{
                        padding: '0.2rem 0.6rem',
                        borderRadius: 999,
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        background: hasTpl ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                        color: hasTpl ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)',
                        border: `1px solid ${hasTpl ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)'}`,
                      }}
                    >
                      {hasTpl ? '✅' : '❌'} {cat} · {n}
                    </span>
                  );
                })}
            </div>
            {missingTemplates.length > 0 && (
              <div className="alert alert-error" style={{ marginTop: '0.6rem', marginBottom: 0 }}>
                <div>
                  ❌ Для «{currentPlatformMeta.name}» не загружен эталонный шаблон (
                  {missingTemplates.join(', ')}). Выгрузка соберётся по встроенному шаблону и может
                  отличаться от кабинета площадки.
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
          </div>
        )}

        {/* Чек-лист 13 канонических полей Ozon */}
        {platform === 'ozon' && (
          <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
            <h4
              style={{ margin: '0 0 0.6rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <Icon name="check" size={16} /> Обязательные поля XLS-шаблона Ozon (13 колонок)
            </h4>
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

        {/* ✅ Превалидация: полоса готовности + дозаполнение дефолтами */}
        {total > 0 && (
          <div className="card" style={{ padding: '0.75rem 1rem', marginBottom: '0.75rem' }}>
            <div
              style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}
            >
              <div className="progress-bar-wrapper" style={{ flex: 1, minWidth: '160px' }}>
                <div
                  className="progress-bar-fill"
                  style={{
                    width: `${readinessPercent}%`,
                    background:
                      readinessPercent >= 80
                        ? 'var(--success, #22c55e)'
                        : readinessPercent >= 40
                          ? 'var(--warning, #f59e0b)'
                          : 'var(--danger, #ef4444)',
                  }}
                />
                <span className="progress-bar-text">{readinessPercent}% готово</span>
              </div>
              <Button
                variant="outline"
                size="small"
                onClick={handleApplyDefaults}
                loading={defaultsLoading}
                disabled={previewLoading || downloadable === total}
                title="Заполнит пустые поля (НДС, ТН ВЭД, габариты, цена) из ваших дефолтов — заполненные значения не трогает"
              >
                <Icon name="edit" size={15} /> Заполнить пропуски дефолтами
              </Button>
            </div>
            {defaultsResult && (
              <div className="alert alert-success" style={{ marginTop: '0.6rem', marginBottom: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Icon name="check" size={15} /> {formatDefaultsResult(defaultsResult)}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ✅ Универсальный список блокирующих полей (любая площадка) */}
        {total > 0 && blockingFields.length > 0 && (
          <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
            <h4
              style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <Icon name="warning" size={16} /> Блокирующие поля ({currentPlatformMeta.name}): что
              не даёт выгрузиться
            </h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
              {blockingFields.slice(0, 10).map((f) => (
                <span
                  key={f.field}
                  title={`Ошибка у ${f.count} товаров`}
                  style={{
                    padding: '0.2rem 0.6rem',
                    borderRadius: 999,
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    background: 'rgba(239,68,68,0.12)',
                    color: 'var(--danger, #ef4444)',
                    border: '1px solid var(--danger, #ef4444)',
                  }}
                >
                  {f.label} · {f.count}
                </span>
              ))}
            </div>
            {blockingFields.some(
              (f) =>
                ['vat_rate', 'okpd_code', 'price'].includes(f.field) ||
                f.field.startsWith('package_')
            ) && (
              <p
                style={{
                  color: 'var(--text-secondary)',
                  fontSize: '0.8rem',
                  margin: '0.5rem 0 0',
                }}
              >
                Часть полей можно заполнить автоматически — кнопка «Заполнить пропуски дефолтами»
                выше.
              </p>
            )}
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
            <p className="empty-state-text">
              {changedSince
                ? 'Новых/изменённых товаров с последней выгрузки нет.'
                : 'Нет товаров с выбранным статусом.'}
            </p>
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
                      #{it.product_id} {it.product_name || it.name}
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
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={handleDownload} disabled={downloaded || loading || downloadable === 0}>
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
