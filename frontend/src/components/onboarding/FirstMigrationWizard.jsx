import React, { useState, useEffect, useRef, useCallback } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { api } from '../../api';
import { GAP_LABELS, BLOCKING_GAP_FIELDS } from '../../constants/gaps';
import { completeWizard, dismissWizardForSession } from './firstMigrationStorage';

/**
 * Мастер первой миграции — проводит новичка по полному циклу
 * «файл площадки → проверка → целевая площадка → перенос → готовый XLSX».
 *
 * Отношение к OnboardingTour: тур показывает ИНТЕРФЕЙС (где что лежит),
 * мастер проводит РЕАЛЬНУЮ операцию с настоящими данными пользователя.
 *
 * Шаги:
 *   welcome → source → check → target → migrate → done
 * Если у пользователя уже есть товары (в т.ч. демо-подложка), шаги
 * source/check пропускаются — начинаем сразу с выбора площадки назначения.
 *
 * Переиспользует рабочие API: previewFileImport/importFromFile/importProducts,
 * migrateBatch + SSE-прогресс (streamTaskProgress), exportXlsxV2 — тот же
 * путь, что и обычные кнопки «Импорт»/«Мигрировать»/«Выгрузка».
 *
 * Закрытие на середине — «Не сейчас»: в этой сессии автопоказ не повторится
 * (sessionStorage), после перезагрузки мастер предложит себя ещё раз.
 * Дошёл до конца — completeWizard() (localStorage, навсегда).
 */

const STEPS = [
  { id: 'welcome', label: 'Начало' },
  { id: 'source', label: 'Откуда' },
  { id: 'check', label: 'Товары' },
  { id: 'target', label: 'Куда' },
  { id: 'migrate', label: 'Перенос' },
  { id: 'done', label: 'Готово' },
];

const HINTS = {
  ozon: 'Тест: test:test · Реальный API: CLIENT_ID:API_KEY',
  wildberries: 'Тест: mock_wb_key (демо-режим)',
  yandex: 'Тест: test:test · API: campaign_id:oauth_token · или ссылка на YML-фид',
  magnit:
    'Магнит Маркет: только XLSX из личного кабинета, лист «SKU». Цен в файле нет — задайте их после импорта.',
  megamarket: 'Мегамаркет: ссылка на YML-фид или XLSX/CSV из личного кабинета.',
  holodilnik: 'Холодильник.ру: ссылка на YML-фид или прайс-лист XLSX/CSV.',
  aliexpress: 'AliExpress: ссылка на YML-фид или XLSX/CSV шаблона массовых операций.',
};

/* Нормализация кадров SSE-прогресса — как в BatchMigrateModal (единый контракт) */
const normalize = (p) => {
  const total = p?.total ?? 0;
  const done = p?.done ?? p?.processed ?? (p?.status === 'completed' ? total : 0) ?? 0;
  return {
    status: p?.status ?? 'pending',
    total,
    done,
    success: p?.success ?? 0,
    errors: p?.errors ?? 0,
    percent: p?.percent ?? (total ? Math.round((done / total) * 100) : 0),
    error: p?.error || '',
  };
};

const isFinished = (n) =>
  n.status === 'completed' ||
  n.status === 'finished' ||
  n.status === 'failed' ||
  (n.total > 0 && n.done >= n.total);

const FirstMigrationWizard = ({ isOpen, onClose, onNotify, onImported, initialProducts = [] }) => {
  const [step, setStep] = useState('welcome');

  // ---------- Шаг «Откуда»: источник и загрузка ----------
  const [sourcePlatform, setSourcePlatform] = useState('ozon');
  const [importMethod, setImportMethod] = useState('file');
  const [authKey, setAuthKey] = useState('');
  const [keyError, setKeyError] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null); // { imported, updated }
  const fileInputRef = useRef(null);

  // ---------- Товары мастера ----------
  const [wizardProducts, setWizardProducts] = useState([]);
  const [hadProductsOnStart, setHadProductsOnStart] = useState(false);
  const [gapChips, setGapChips] = useState(null); // [[label, count], ...] или null

  // ---------- Шаг «Куда» ----------
  const [targetPlatform, setTargetPlatform] = useState('wildberries');

  // ---------- Шаг «Перенос» ----------
  const [batch, setBatch] = useState(null);
  const [prog, setProg] = useState(null);
  const [finished, setFinished] = useState(false);
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState('');

  // ---------- Шаг «Готово»: экспорт ----------
  const [exporting, setExporting] = useState(false);
  const [exportFilename, setExportFilename] = useState(null);
  const [exportError, setExportError] = useState('');

  const sourceMeta = PLATFORMS.find((p) => p.id === sourcePlatform) || PLATFORMS[0];
  const targetMeta = PLATFORMS.find((p) => p.id === targetPlatform) || PLATFORMS[1];

  // ==================== Сброс при открытии ====================
  useEffect(() => {
    if (!isOpen) return;
    setStep('welcome');
    setSourcePlatform('ozon');
    setImportMethod('file');
    setAuthKey('');
    setKeyError('');
    setSelectedFile(null);
    setIsDragging(false);
    setPreview(null);
    setPreviewLoading(false);
    setPreviewError('');
    setImporting(false);
    setImportResult(null);
    setTargetPlatform('wildberries');
    setBatch(null);
    setProg(null);
    setFinished(false);
    setStarting(false);
    setRunError('');
    setExporting(false);
    setExportFilename(null);
    setExportError('');
    setGapChips(null);
    // Товары берём только в момент открытия (refresh списка произойдёт
    // после импорта отдельным запросом) — поэтому без initialProducts в deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const initial = Array.isArray(initialProducts) ? initialProducts : [];
    setWizardProducts(initial);
    setHadProductsOnStart(initial.length > 0);
  }, [isOpen]);

  // ==================== Навигация по шагам ====================
  const visibleSteps = hadProductsOnStart
    ? STEPS.filter((s) => !['source', 'check'].includes(s.id))
    : STEPS;
  const stepIndex = visibleSteps.findIndex((s) => s.id === step);

  const startWizard = () => setStep(hadProductsOnStart ? 'target' : 'source');

  const handleClose = useCallback(() => {
    // Закрытие на середине — «Не сейчас»: в этой сессии автопоказ не повторится
    // (sessionStorage — переживёт F5, сотрётся при закрытии вкладки)
    if (step !== 'done') {
      dismissWizardForSession();
      onNotify?.(
        'Мастер можно запустить позже: кнопка «Мастер первой миграции» на странице «Товары».'
      );
    }
    onClose?.();
  }, [step, onClose, onNotify]);

  // ==================== Импорт: файл ====================
  const changeSourcePlatform = (id) => {
    setSourcePlatform(id);
    setSelectedFile(null);
    setPreview(null);
    setPreviewError('');
    setAuthKey('');
    setKeyError('');
    const methods = PLATFORMS.find((p) => p.id === id)?.importMethods || ['key', 'file'];
    if (!methods.includes(importMethod)) setImportMethod(methods[0]);
  };

  const loadPreview = async (file) => {
    setSelectedFile(file);
    setPreview(null);
    setPreviewError('');
    setPreviewLoading(true);
    try {
      const data = await api.previewFileImport(sourcePlatform, file);
      if (!data.success) throw new Error(data.detail || 'Не удалось прочитать файл');
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

  // ==================== Завершение импорта (общий хвост) ====================
  const finishImport = async (data, keyMode = false) => {
    const imported = data.imported ?? 0;
    const updated = data.updated ?? 0;
    if (!data.success && imported === 0 && !keyMode) {
      throw new Error(data.detail || data.message || 'Импорт не удался');
    }
    setImportResult({ imported, updated });

    // Свежий список товаров + пропуски — мастер живёт своими данными,
    // независимо от кэша App (React Query обновится параллельно).
    try {
      const list = await api.getProducts({ sort: 'newest', limit: 50, source: 'all' });
      setWizardProducts(list.products || []);
      try {
        const gaps = await api.getGaps('all');
        const entries = Object.entries(gaps?.gaps || {})
          .filter(([, n]) => n > 0)
          .sort((a, b) => b[1] - a[1]);
        // Три габарита схлопываем в один чип «Габариты, мм» (как в GapsBanner);
        // третий элемент чипа — блокирует ли пропуск миграцию (цена/фото)
        const dims = ['package_width_mm', 'package_height_mm', 'package_length_mm'];
        const chips = [];
        entries.forEach(([k, n]) => {
          if (dims.includes(k) && chips.some(([label]) => label === 'Габариты, мм')) return;
          chips.push([
            dims.includes(k) ? 'Габариты, мм' : GAP_LABELS[k] || k,
            n,
            BLOCKING_GAP_FIELDS.includes(k),
          ]);
        });
        setGapChips(chips.slice(0, 4));
      } catch {
        setGapChips(null); // пропуски — необязательная декорация
      }
    } catch {
      /* список не поднялся — идём дальше с числом импортированных */
    }

    onImported?.();
    setStep('check');
  };

  const confirmFileImport = async () => {
    if (!selectedFile || importing) return;
    setImporting(true);
    setPreviewError('');
    try {
      const data = await api.importFromFile(sourcePlatform, selectedFile, 'create');
      await finishImport(data);
    } catch (e) {
      setPreviewError(e.message);
    } finally {
      setImporting(false);
    }
  };

  const confirmKeyImport = async () => {
    const v = authKey.trim();
    if (!v) {
      setKeyError('Укажите ключ или ссылку');
      return;
    }
    if (v.length < 3) {
      setKeyError('Слишком короткое значение');
      return;
    }
    const full =
      v.startsWith('http://') ||
      v.startsWith('https://') ||
      (v.includes(':') && v.split(':')[0].toLowerCase() === sourcePlatform)
        ? v
        : `${sourcePlatform}:${v}`;
    setImporting(true);
    setKeyError('');
    try {
      const data = await api.importProducts(full);
      await finishImport(data, true);
    } catch (e) {
      setKeyError(e.message);
    } finally {
      setImporting(false);
    }
  };

  // ==================== Запуск переноса ====================
  const startMigration = async () => {
    const ids = (wizardProducts || []).map((p) => p.id).filter((id) => id > 0);
    if (!ids.length) {
      setRunError('Не найдено товаров для переноса. Вернитесь и загрузите файл.');
      return;
    }
    // Сразу на шаг «Перенос»: и прогресс, и ошибка запуска видны там
    setStep('migrate');
    setStarting(true);
    setRunError('');
    try {
      const res = await api.migrateBatch(ids, targetPlatform);
      const batchId = res?.batch_id || res?.task_id || res?.id;
      if (!batchId) throw new Error('Сервер не вернул ID задачи (batch_id)');
      setBatch({ batch_id: batchId, total: res?.total ?? ids.length });
    } catch (e) {
      setRunError(e.message || 'Не удалось запустить перенос');
      // Остаются на шаге «Перенос»: ошибка видна, кнопка «Назад» возвращает
      // к выбору площадки (batch ещё не установлен).
    } finally {
      setStarting(false);
    }
  };

  // ==================== Прогресс переноса: SSE + резерв-polling ====================
  useEffect(() => {
    const batchId = batch?.batch_id || batch?.id;
    if (!batchId || finished) return undefined;

    const ac = new AbortController();
    const onUpdate = (raw) => {
      const n = normalize(raw);
      setProg(n);
      if (n.error) setRunError(n.error);
      if (isFinished(n)) setFinished(true);
    };

    api
      .streamTaskProgress(batchId, {
        onUpdate,
        onError: (e) => setRunError(`Связь с сервером: ${e.message} (продолжаем пробовать)`),
        timeoutMs: 30 * 60 * 1000,
        timeoutMessage: 'Таймаут ожидания переноса (30 мин). Проверьте логи Celery.',
        pollIntervalMs: 1500,
        signal: ac.signal,
      })
      .catch((e) => {
        if (!ac.signal.aborted) setRunError('Ошибка отслеживания прогресса: ' + e.message);
      });

    return () => ac.abort();
  }, [batch, finished]);

  // Завершение переноса → обновляем данные App и переходим к финалу
  useEffect(() => {
    if (!finished || step !== 'migrate') return;
    onImported?.();
    setStep('done');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished]);

  // ==================== Экспорт файла ====================
  const downloadResult = async () => {
    setExporting(true);
    setExportError('');
    try {
      const filename = await api.exportXlsxV2(targetPlatform, 'success');
      setExportFilename(filename);
    } catch (e) {
      setExportError(e.message);
    } finally {
      setExporting(false);
    }
  };

  const finishWizard = () => {
    completeWizard();
    onClose?.();
  };

  if (!isOpen) return null;

  const n = prog || {
    total: batch?.total ?? wizardProducts.length,
    done: 0,
    success: 0,
    errors: 0,
    percent: 0,
  };
  const percent = Math.min(100, n.percent || 0);
  const migrationBusy = step === 'migrate' && batch && !finished;
  const canClose = !migrationBusy && !importing;

  /* Есть ли блокирующие пропуски (цена = 0 / нет главного фото) — такие
   * карточки валидатор площадки отклонит, предупреждаем заранее */
  const blockingGapWarning = gapChips?.some(([, , isBlocking]) => isBlocking) || false;

  return (
    <div
      className="modal-overlay"
      onClick={() => canClose && handleClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Мастер первой миграции"
    >
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <span style={{ color: 'var(--accent-primary)', display: 'inline-flex' }}>
              <Icon name="migrate" size={22} />
            </span>
            Мастер первой миграции
          </h2>
          {canClose && (
            <button type="button" className="close-btn" onClick={handleClose} title="Закрыть">
              <Icon name="close" size={16} />
            </button>
          )}
        </div>

        {/* Степпер — скрываем на welcome (там своя «карта шагов») */}
        {step !== 'welcome' && (
          <div className="wizard-steps">
            {visibleSteps
              .filter((s) => s.id !== 'welcome')
              .map((s, i) => (
                <span
                  key={s.id}
                  className={`wizard-step ${
                    s.id === step ? 'active' : i + 1 < stepIndex ? 'done' : ''
                  }`}
                >
                  {i + 1 < stepIndex ? <Icon name="check" size={12} /> : <b>{i + 1}</b>}
                  {s.label}
                </span>
              ))}
          </div>
        )}

        {/* ==================== Шаг 0: приветствие ==================== */}
        {step === 'welcome' && (
          <>
            <div className="wizard-welcome">
              <div className="wizard-welcome-icon">
                <Icon name="migrate" size={40} />
              </div>
              <h3>Перенесём ваши товары за 5 шагов</h3>
              <p className="wizard-welcome-sub">
                {hadProductsOnStart
                  ? `У вас уже есть ${wizardProducts.length} товаров — начнём сразу с выбора площадки назначения.`
                  : 'Загрузите выгрузку из кабинета площадки — мастер проведёт до готового файла для новой площадки.'}
              </p>
              <div className="wizard-plan">
                {!hadProductsOnStart && (
                  <>
                    <div className="wizard-plan-item">
                      <span className="wizard-plan-num">1</span>
                      <Icon name="import" size={16} />
                      <span>Откуда: файл или API-ключ площадки</span>
                    </div>
                    <div className="wizard-plan-item">
                      <span className="wizard-plan-num">2</span>
                      <Icon name="products" size={16} />
                      <span>Проверка товаров и пропусков</span>
                    </div>
                  </>
                )}
                <div className="wizard-plan-item">
                  <span className="wizard-plan-num">{hadProductsOnStart ? 1 : 3}</span>
                  <Icon name="migrate" size={16} />
                  <span>Куда: площадка назначения</span>
                </div>
                <div className="wizard-plan-item">
                  <span className="wizard-plan-num">{hadProductsOnStart ? 2 : 4}</span>
                  <Icon name="layers" size={16} />
                  <span>Перенос карточек с прогрессом</span>
                </div>
                <div className="wizard-plan-item">
                  <span className="wizard-plan-num">{hadProductsOnStart ? 3 : 5}</span>
                  <Icon name="export" size={16} />
                  <span>Готовый XLSX для кабинета площадки</span>
                </div>
              </div>
              <p className="wizard-welcome-note">
                Ничего не сломается: исходные карточки остаются, перенос создаёт копию под формат
                новой площадки.
              </p>
            </div>
            <div className="modal-actions">
              <Button variant="outline" onClick={handleClose}>
                Не сейчас
              </Button>
              <Button onClick={startWizard} autoFocus>
                Начать <Icon name="chevron-right" size={16} />
              </Button>
            </div>
          </>
        )}

        {/* ==================== Шаг 1: откуда ==================== */}
        {step === 'source' && (
          <>
            <label className="form-label">1. Площадка-источник:</label>
            <div className="platform-selector">
              {PLATFORMS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`platform-btn ${sourcePlatform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => changeSourcePlatform(p.id)}
                >
                  <div
                    className="platform-logo"
                    style={{
                      backgroundColor: sourcePlatform === p.id ? p.color : 'var(--bg-tertiary)',
                      color: sourcePlatform === p.id ? 'white' : 'var(--text-muted)',
                    }}
                  >
                    {p.logoText}
                  </div>
                  <span>{p.name}</span>
                </button>
              ))}
            </div>

            <label className="form-label">2. Загрузка товаров:</label>
            <div className="import-method-toggle">
              <button
                type="button"
                className={`toggle-btn ${importMethod === 'file' ? 'active' : ''}`}
                onClick={() => setImportMethod('file')}
              >
                <Icon name="file" size={16} /> Excel / CSV
              </button>
              <button
                type="button"
                className={`toggle-btn ${importMethod === 'key' ? 'active' : ''}`}
                onClick={() => setImportMethod('key')}
                disabled={
                  !((sourceMeta.importMethods || ['key', 'file']).includes('key') ? true : false)
                }
              >
                <Icon name="key" size={16} /> API ключ / YML
              </button>
            </div>

            {importMethod === 'key' ? (
              <>
                <div className="modal-hint-box">
                  <span className="hint-icon">
                    <Icon name="info" size={18} />
                  </span>
                  <p>{HINTS[sourcePlatform] || HINTS.ozon}</p>
                </div>
                <label className="form-label">Ключ или ссылка</label>
                <input
                  className={`form-input ${keyError ? 'input-error' : ''}`}
                  type="text"
                  value={authKey}
                  onChange={(e) => {
                    setAuthKey(e.target.value);
                    setKeyError('');
                  }}
                  placeholder="test:test или https://.../yml.xml"
                />
                {keyError && <div className="input-error-message">{keyError}</div>}
              </>
            ) : (
              <>
                {!preview && !previewLoading && (
                  <>
                    <div className="modal-hint-box">
                      <span className="hint-icon">
                        <Icon name="info" size={18} />
                      </span>
                      <p>{HINTS[sourcePlatform] || HINTS.ozon}</p>
                    </div>
                    <div
                      className={`drop-zone ${isDragging ? 'dragging' : ''}`}
                      onDragOver={(e) => {
                        e.preventDefault();
                        setIsDragging(true);
                      }}
                      onDragLeave={(e) => {
                        e.preventDefault();
                        setIsDragging(false);
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        setIsDragging(false);
                        pickFile(e.dataTransfer.files?.[0]);
                      }}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <div className="drop-zone-icon">
                        <Icon name="file" size={44} />
                      </div>
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
                  </>
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
                    <div className="spinner spinner-dark" />
                    Читаем файл и строим предпросмотр...
                  </div>
                )}

                {preview && (
                  <div className="preview-section">
                    <div className="preview-summary">
                      <span>
                        Строк в файле: <b>{preview.total_estimated}</b>
                      </span>
                      <span>
                        Будет импортировано: <b>{preview.valid_estimated}</b>
                      </span>
                      <span>
                        Ошибок: <b>{preview.errors?.length || 0}</b>
                      </span>
                    </div>
                    <div className="preview-table-wrap">
                      <table className="preview-table">
                        <thead>
                          <tr>
                            {(preview.columns || []).slice(0, 6).map((c) => (
                              <th key={c}>{c}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(preview.preview || []).slice(0, 3).map((row, i) => (
                            <tr key={i}>
                              {(preview.columns || []).slice(0, 6).map((c) => (
                                <td key={c} title={String(row[c] ?? '')}>
                                  {String(row[c] ?? '').slice(0, 40)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {(preview.errors?.length || 0) > 0 && (
                      <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                        ⚠ Строк с ошибками: {preview.errors.length} — они будут пропущены.
                      </p>
                    )}
                  </div>
                )}
              </>
            )}

            {previewError && (
              <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
                <div>{previewError}</div>
              </div>
            )}

            <div className="modal-actions">
              <Button variant="outline" onClick={handleClose}>
                Не сейчас
              </Button>
              {importMethod === 'file' ? (
                <Button
                  onClick={confirmFileImport}
                  disabled={importing || !selectedFile || preview?.valid_estimated === 0}
                  loading={importing}
                >
                  <Icon name="import" size={16} />
                  {importing
                    ? 'Импортируем...'
                    : preview
                      ? `Импортировать ${preview.valid_estimated}`
                      : 'Импортировать файл'}
                </Button>
              ) : (
                <Button onClick={confirmKeyImport} disabled={importing} loading={importing}>
                  <Icon name="import" size={16} /> Импортировать
                </Button>
              )}
            </div>
          </>
        )}

        {/* ==================== Шаг 2: проверка товаров ==================== */}
        {step === 'check' && (
          <>
            <h3 className="wizard-h">
              <Icon name="products" size={18} /> Товары загружены
            </h3>
            <div className="wizard-summary">
              <div className="wizard-stat">
                <div className="stat-label">Импортировано</div>
                <div className="stat-value success-text">
                  {importResult?.imported ?? wizardProducts.length}
                </div>
              </div>
              {!!importResult?.updated && (
                <div className="wizard-stat">
                  <div className="stat-label">Обновлено</div>
                  <div className="stat-value">{importResult.updated}</div>
                </div>
              )}
              <div className="wizard-stat">
                <div className="stat-label">Всего в каталоге</div>
                <div className="stat-value">{wizardProducts.length}</div>
              </div>
            </div>

            {wizardProducts.length > 0 && (
              <div className="wizard-product-list">
                {wizardProducts.slice(0, 5).map((p) => (
                  <div key={p.id} className="wizard-product-row">
                    <Icon name="box" size={14} />
                    <span className="wizard-product-name">
                      {p.title || p.name || `Товар #${p.id}`}
                    </span>
                    {Number(p.price) > 0 && (
                      <span className="wizard-product-price">{p.price} ₽</span>
                    )}
                  </div>
                ))}
                {wizardProducts.length > 5 && (
                  <div className="wizard-product-row wizard-product-more">
                    …и ещё {wizardProducts.length - 5}
                  </div>
                )}
              </div>
            )}

            {gapChips && gapChips.length > 0 ? (
              <div className={`modal-hint-box ${blockingGapWarning ? 'wizard-hint-warning' : ''}`}>
                <span className="hint-icon">
                  <Icon name={blockingGapWarning ? 'alert' : 'info'} size={18} />
                </span>
                <p>
                  Незаполненные поля: {gapChips.map(([l, c]) => `${l} — у ${c}`).join(', ')}.{' '}
                  {blockingGapWarning
                    ? 'Цена и фото обязательны для выгрузки — дозаполните их после мастера (кнопка «Дефолты» и редактирование карточек).'
                    : 'Пустые необязательные поля миграция заполнит значениями по умолчанию.'}
                </p>
              </div>
            ) : (
              <div className="modal-hint-box">
                <span className="hint-icon">
                  <Icon name="check" size={18} />
                </span>
                <p>Все обязательные поля заполнены — можно переносить.</p>
              </div>
            )}

            <div className="modal-actions">
              <Button variant="outline" onClick={() => setStep('source')}>
                <Icon name="chevron-left" size={16} /> Другой файл
              </Button>
              <Button onClick={() => setStep('target')} disabled={!wizardProducts.length} autoFocus>
                Выбрать площадку <Icon name="chevron-right" size={16} />
              </Button>
            </div>
          </>
        )}

        {/* ==================== Шаг 3: куда ==================== */}
        {step === 'target' && (
          <>
            <h3 className="wizard-h">
              <Icon name="migrate" size={18} /> Куда переносим
            </h3>
            <p className="wizard-sub">
              Сервис сопоставит категории, адаптирует карточки и характеристики под формат личного
              кабинета выбранной площадки.
            </p>
            <label className="form-label">Площадка назначения:</label>
            <div className="platform-selector">
              {PLATFORMS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`platform-btn ${targetPlatform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => setTargetPlatform(p.id)}
                >
                  <div
                    className="platform-logo"
                    style={{
                      backgroundColor: targetPlatform === p.id ? p.color : 'var(--bg-tertiary)',
                      color: targetPlatform === p.id ? 'white' : 'var(--text-muted)',
                    }}
                  >
                    {p.logoText}
                  </div>
                  <span>{p.name}</span>
                </button>
              ))}
            </div>

            {sourcePlatform === targetPlatform && !hadProductsOnStart && (
              <div className="modal-hint-box">
                <span className="hint-icon">
                  <Icon name="info" size={18} />
                </span>
                <p>
                  Источник и назначение совпадают: карточки будут заново приведены к формату{' '}
                  {targetMeta.name}. Обычно мигрируют на другую площадку.
                </p>
              </div>
            )}

            <div className="modal-actions">
              {!hadProductsOnStart && (
                <Button variant="outline" onClick={() => setStep('check')}>
                  <Icon name="chevron-left" size={16} /> Назад
                </Button>
              )}
              <Button
                onClick={startMigration}
                disabled={starting || !wizardProducts.length}
                loading={starting}
                autoFocus
              >
                <Icon name="migrate" size={16} /> Перенести {wizardProducts.length} товаров на{' '}
                {targetMeta.name}
              </Button>
            </div>
          </>
        )}

        {/* ==================== Шаг 4: перенос ==================== */}
        {step === 'migrate' && (
          <>
            <h3 className="wizard-h">
              <Icon name="layers" size={18} /> Переносим на {targetMeta.name}
            </h3>

            {!batch && !runError && <p className="wizard-sub">Запускаем задачу переноса…</p>}

            {batch && (
              <>
                <div className="progress-bar-wrapper">
                  <div className="progress-bar-fill" style={{ width: `${percent}%` }} />
                  <span className="progress-bar-text">{percent}%</span>
                </div>
                <div className="progress-stats">
                  <div className="stat-item">
                    <div className="stat-label">Всего</div>
                    <div className="stat-value">{n.total}</div>
                  </div>
                  <div className="stat-item">
                    <div className="stat-label">Готово</div>
                    <div className="stat-value">{n.done}</div>
                  </div>
                  <div className="stat-item">
                    <div className="stat-label">Успешно</div>
                    <div className="stat-value success-text">{n.success}</div>
                  </div>
                  <div className="stat-item">
                    <div className="stat-label">Ошибки</div>
                    <div className="stat-value error-text">{n.errors}</div>
                  </div>
                </div>
                {!finished && (
                  <p className="progress-status">
                    Переносим карточки… окно можно закрыть — процесс продолжится на сервере.
                  </p>
                )}
              </>
            )}

            {runError && (
              <div className="alert alert-error">
                <div>{runError}</div>
              </div>
            )}

            <div className="modal-actions">
              {!batch && (
                <Button variant="outline" onClick={() => setStep('target')} disabled={starting}>
                  <Icon name="chevron-left" size={16} /> Назад
                </Button>
              )}
              {/* Переход к финалу — автоматический (useEffect по finished):
                   пользователь сразу видит сводку и кнопку скачивания */}
            </div>
          </>
        )}

        {/* ==================== Шаг 5: готово ==================== */}
        {step === 'done' && (
          <>
            <div className="wizard-done">
              <div className="wizard-done-icon">
                <Icon name="check" size={40} />
              </div>
              <h3>Перенос завершён</h3>
              <div className="wizard-summary">
                <div className="wizard-stat">
                  <div className="stat-label">Успешно</div>
                  <div className="stat-value success-text">{n.success}</div>
                </div>
                <div className="wizard-stat">
                  <div className="stat-label">С ошибками</div>
                  <div className="stat-value error-text">{n.errors}</div>
                </div>
                <div className="wizard-stat">
                  <div className="stat-label">Площадка</div>
                  <div className="stat-value">{targetMeta.name}</div>
                </div>
              </div>

              {n.success > 0 && (
                <p className="wizard-sub">
                  Скачайте файл и загрузите его в кабинете {targetMeta.name} — товары появятся на
                  новой площадке.
                </p>
              )}
              {n.errors > 0 && (
                <div className="modal-hint-box wizard-hint-warning">
                  <span className="hint-icon">
                    <Icon name="alert" size={18} />
                  </span>
                  <p>
                    {n.errors} карточек отклонены (не хватило обязательных полей). Найдёте их в
                    разделе «Товары» с фильтром «Ошибка» — дозаполните и мигрируйте повторно.
                  </p>
                </div>
              )}
            </div>

            {exportFilename && (
              <div className="alert alert-success">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Icon name="check" size={16} /> Файл «{exportFilename}» скачан
                  {exportFilename.toLowerCase().endsWith('.zip') &&
                    ' — ZIP: у каждой категории свой шаблон, загружайте файлы по отдельности'}
                </div>
              </div>
            )}
            {exportError && (
              <div className="alert alert-error">
                <div>
                  {exportError}
                  <div style={{ marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
                    Файл можно скачать позже: раздел «Товары» → «Выгрузка».
                  </div>
                </div>
              </div>
            )}

            <div className="modal-actions">
              {n.success > 0 && (
                <Button
                  variant="outline"
                  onClick={downloadResult}
                  disabled={exporting}
                  loading={exporting}
                >
                  <Icon name="export" size={16} />
                  {exportFilename ? 'Скачать снова' : 'Скачать файл для кабинета'}
                </Button>
              )}
              <Button onClick={finishWizard} autoFocus>
                Завершить
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default FirstMigrationWizard;
