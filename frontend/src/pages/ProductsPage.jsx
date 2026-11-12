import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import EmptyState from '../components/common/EmptyState';
import DeleteConfirmModal from '../components/products/DeleteConfirmModal';
import DefaultsModal from '../components/products/DefaultsModal';
import BulkUpdateModal from '../components/products/BulkUpdateModal';
import BatchTnvedModal from '../components/products/BatchTnvedModal';
import ProductsTable from '../components/products/ProductsTable';
import Pagination from '../components/products/Pagination';
import GapsBanner from '../components/products/GapsBanner';
import { useColumnResize } from '../components/products/useColumnResize';
import { SORT_OPTIONS } from '../components/products/tableUtils';
import {
  computeSelectedGaps,
  selectedBlockingTotal,
  selectedFillableTotal,
} from '../components/products/gapsHelpers';
import { api } from '../api';
import { FILLED_LABELS } from '../constants/gaps';

/* Страница «Товары».
 *
 * Р4: монолит ProductsPage.jsx (1095 строк) разбит — таблица в
 * components/products/ProductsTable.jsx, пагинация в Pagination.jsx,
 * баннер пропусков в GapsBanner.jsx (+ чистые gapsHelpers.js),
 * ресайз колонок в useColumnResize.js, константы в tableUtils.js.
 * Здесь осталась только оркестрация: состояние, CRUD-хендлеры, layout.
 */
const ProductsPage = ({
  isAdmin = false,
  refreshKey = 0,
  onMigrate,
  onLogistics,
  onAttributes,
  onVariants,
  onPhotos,
  onExport,
  onImport,
}) => {
  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState('newest');
  const [skip, setSkip] = useState(0);
  const [limit, setLimit] = useState(50);

  const { colWidths, setColWidths, colStyle, Resizer } = useColumnResize();

  const [selected, setSelected] = useState([]);
  const [deleteMode, setDeleteMode] = useState(null);
  const [deleteTargetId, setDeleteTargetId] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const [showBulkUpdate, setShowBulkUpdate] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [undoAvailable, setUndoAvailable] = useState(false); // после успешного bulk-update
  const [undoLoading, setUndoLoading] = useState(false);

  // ✅ v4: массовый подбор ТН ВЭД для выделенных
  const [showTnved, setShowTnved] = useState(false);

  const [showDefaults, setShowDefaults] = useState(false);
  const [gaps, setGaps] = useState(null);
  const [applyLoading, setApplyLoading] = useState(false);
  const [specNames, setSpecNames] = useState([]);

  // ==================== Загрузка ====================
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const d = await api.getProducts({
        search: search || undefined,
        status: status === 'all' ? undefined : status,
        source: 'all',
        sort,
        skip,
        limit,
      });
      setProducts(d.products || []);
      setTotal(d.total ?? (d.products || []).length);
      console.log('✅ ProductsPage: loaded', d.products?.length || 0, 'products');
    } catch (e) {
      setError(e.message);
      console.error('❌ ProductsPage: load error', e);
    } finally {
      setLoading(false);
    }
  }, [search, status, sort, skip, limit]);

  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  }, [load]);
  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (refreshKey > 0) {
      console.log('🔄 ProductsPage: refreshKey changed to', refreshKey, '- reloading...');
      loadRef.current();
    }
  }, [refreshKey]);

  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(''), 5000);
    return () => clearTimeout(t);
  }, [message]);

  // ✅ Загрузка счётчика пропусков
  const loadGaps = useCallback(async () => {
    try {
      const g = await api.getGaps('all');
      setGaps(g);
    } catch {
      setGaps(null);
    }
  }, []);

  const loadSpecNames = useCallback(async () => {
    try {
      const names = await api.getSpecNames('ozon');
      setSpecNames(Array.isArray(names) ? names : []);
    } catch {
      setSpecNames([]);
    }
  }, []);

  useEffect(() => {
    loadGaps();
    loadSpecNames();
  }, [refreshKey, loadGaps, loadSpecNames]);

  // ✅ v4: есть ли неотменённые операции правок (баннер «Отменить последнее изменение»)
  useEffect(() => {
    api
      .getEditHistory(1)
      .then((d) => setUndoAvailable(!!d.has_undo))
      .catch(() => setUndoAvailable(false));
  }, [refreshKey]);

  // ==================== Выделение ====================
  const toggleOne = (id) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };
  const toggleAll = () => {
    const ids = products.map((p) => p.id);
    setSelected((prev) => (ids.length > 0 && ids.every((id) => prev.includes(id)) ? [] : ids));
  };

  // ==================== Удаление ====================
  const handleDeleteConfirm = async () => {
    setDeleteLoading(true);
    try {
      if (deleteMode === 'all') {
        const r = await api.deleteAllProducts();
        setMessage(`Удалено товаров: ${r.deleted}`);
        setSelected([]);
      } else if (deleteMode === 'bulk') {
        const r = await api.bulkDeleteProducts(selected);
        setMessage(`Удалено: ${r.deleted}${r.skipped ? `, пропущено (чужие): ${r.skipped}` : ''}`);
        setSelected([]);
      } else {
        await api.deleteProduct(deleteTargetId);
        setMessage('Товар удалён');
        setSelected((prev) => prev.filter((id) => id !== deleteTargetId));
      }
      setDeleteMode(null);
      setDeleteTargetId(null);
      await load();
    } catch (e) {
      setError(e.message);
      setDeleteMode(null);
      setDeleteTargetId(null);
    } finally {
      setDeleteLoading(false);
    }
  };

  // ==================== Массовое обновление (+ undo) ====================
  const handleBulkUpdate = async (payload) => {
    setBulkLoading(true);
    try {
      const r = await api.bulkUpdateProducts({ product_ids: selected, ...payload });
      let msg = `Обновлено товаров: ${r.updated}`;
      if (r.category_warning) msg += ` · ⚠ ${r.category_warning}`;
      setMessage(msg);
      setShowBulkUpdate(false);
      setSelected([]);
      setUndoAvailable(true); // ← показать кнопку «Отменить»
      await load();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkUndo = async () => {
    setUndoLoading(true);
    try {
      const r = await api.bulkUndoProducts();
      setMessage(
        `↩ Отменено${r.label ? ` (${r.label})` : ''}: прежние значения восстановлены у ${r.restored} товаров` +
          (r.skipped_missing ? ` (пропущено удалённых: ${r.skipped_missing})` : '')
      );
      // Могут остаться другие неотменённые операции — сверяемся с историей
      const d = await api.getEditHistory(1).catch(() => ({ has_undo: false }));
      setUndoAvailable(!!d.has_undo);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setUndoLoading(false);
    }
  };

  // ==================== Дозаполнение пропусков ====================
  const handleApplyDefaults = async (mode = 'all') => {
    setApplyLoading(true);
    try {
      const r = await api.applyDefaults(mode === 'selected' ? { product_ids: selected } : 'all');
      // r.fields — счётчик ЗАПОЛНЕННЫХ полей (не пропусков!), поэтому подписываем
      // метками действий: «подставлено: цена — 3», а не «Цена = 0: 3»
      const summary = Object.entries(r.fields || {})
        .map(([k, v]) => `${FILLED_LABELS[k] || k} — ${v}`)
        .join(', ');
      setMessage(
        `Дозаполнено товаров: ${r.updated} из ${r.total}` +
          (summary ? ` · подставлено: ${summary}` : '')
      );
      if (r.updated > 0) setUndoAvailable(true); // ✅ v4: дозаполнение можно отменить
      if (mode === 'selected') setSelected([]);
      await loadGaps();
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setApplyLoading(false);
    }
  };

  // ✅ Миграция с проверкой пропусков в выделенных товарах
  const handleMigrateSelected = () => {
    if (!onMigrate || selected.length === 0) return;

    // Считаем пропуски среди ВЫДЕЛЕННЫХ
    const selectedProducts = products.filter((p) => selected.includes(p.id));
    const localGaps = { price: 0, main_photo: 0 };
    selectedProducts.forEach((p) => {
      const price = Number(p.price);
      if (!price || price <= 0 || isNaN(price)) localGaps.price += 1;
      if (!p.photos || p.photos.length === 0) localGaps.main_photo += 1;
    });
    const blockingCount = (localGaps.price || 0) + (localGaps.main_photo || 0);

    if (blockingCount > 0) {
      const lines = [];
      if (localGaps.price) lines.push(`— Цена 0/пустая: ${localGaps.price} шт.`);
      if (localGaps.main_photo) lines.push(`— Нет главного фото: ${localGaps.main_photo} шт.`);
      const msg =
        `⚠️ В ${blockingCount} из ${selected.length} выделенных товаров есть блокирующие пропуски:\n\n` +
        lines.join('\n') +
        `\n\nПродолжить миграцию? Товары с пропусками будут отклонены валидатором.`;

      if (!window.confirm(msg)) return;
    }
    onMigrate(selected);
  };

  // ==================== Категории текущих товаров ====================
  const productCategories = useMemo(
    () =>
      Array.from(
        new Set(products.map((p) => p.mapped_category || p.category).filter(Boolean))
      ).sort(),
    [products]
  );

  const gapEntries = gaps ? Object.entries(gaps.gaps || {}).filter(([, n]) => n > 0) : [];

  // ✅ Пропуски в ВЫДЕЛЕННЫХ товарах (для панели массовых действий)
  const selGaps = useMemo(() => computeSelectedGaps(products, selected), [products, selected]);
  const selBlockingTotal = selectedBlockingTotal(selGaps);
  const selFillableTotal = selectedFillableTotal(selGaps);

  const page = Math.floor(skip / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));

  return (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">Товары</h1>
          <p className="header-subtitle">Каталог, миграция и выгрузка на площадки</p>
        </div>
        <div className="header-actions">
          {onImport && (
            <Button onClick={onImport} data-onboarding="import-btn">
              <Icon name="import" size={16} /> Импорт
            </Button>
          )}
          {onExport && (
            <Button variant="secondary" onClick={onExport} data-onboarding="export-btn">
              <Icon name="export" size={16} /> Выгрузка
            </Button>
          )}
        </div>
      </header>

      {/* ==================== Баннер пропусков ==================== */}
      <GapsBanner
        gaps={gaps}
        gapEntries={gapEntries}
        products={products}
        selected={selected}
        applyLoading={applyLoading}
        onApplyDefaults={handleApplyDefaults}
      />

      {/* ==================== Фильтры + сброс ширины колонок ==================== */}
      <div
        className="products-toolbar"
        style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}
      >
        <input
          className="form-input"
          placeholder="Поиск: название, SKU, артикул…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setSkip(0);
          }}
          style={{ flex: 1, minWidth: 200 }}
        />
        <select
          className="form-input"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setSkip(0);
          }}
          style={{ width: 'auto' }}
        >
          <option value="all">Все статусы</option>
          <option value="pending">Ожидает</option>
          <option value="processing">В работе</option>
          <option value="success">Успешно</option>
          <option value="error">Ошибка</option>
        </select>
        <select
          className="form-input"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            setSkip(0);
          }}
          style={{ width: 'auto' }}
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {Object.keys(colWidths).length > 0 && (
          <Button
            variant="outline"
            size="small"
            title="Вернуть ширину всех колонок к стандартной"
            onClick={() => setColWidths({})}
          >
            <Icon name="refresh" size={14} /> Сбросить ширину колонок
          </Button>
        )}

        <Button
          variant="secondary"
          onClick={() => setShowDefaults(true)}
          data-onboarding="defaults-btn"
        >
          <Icon name="settings" size={16} /> Дефолты
        </Button>

        {/* Обновить список — иконкой: текст на кнопке не добавлял смысла */}
        <Button
          variant="outline"
          size="small"
          className="btn-icon"
          onClick={load}
          disabled={loading}
          title="Обновить список товаров"
        >
          <Icon name="refresh" size={19} />
        </Button>

        {/* Опасная операция — ушла из шапки в тулбар, чтобы не висела рядом
            с «Импорт»/«Выгрузка» и не создавала визуальный шум */}
        <Button
          variant="outline"
          size="small"
          className="btn-danger-outline"
          onClick={() => setDeleteMode('all')}
          title={
            isAdmin
              ? 'Удалить ВСЕ товары в системе (с подтверждением)'
              : 'Удалить все мои товары (с подтверждением)'
          }
        >
          <Icon name="trash" size={15} /> Удалить все
        </Button>
      </div>

      {error && (
        <div className="alert alert-error">
          <div>{error}</div>
        </div>
      )}
      {message && (
        <div className="alert alert-success">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Icon name="check" size={16} /> {message}
          </div>
        </div>
      )}

      {/* ✅ Undo последней операции правки (масс. обновление / ТН ВЭД / правка / логистика) */}
      {undoAvailable && (
        <div className="alert alert-success bulk-undo-alert">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Icon name="refresh" size={16} /> Последнюю операцию правки можно отменить
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Button size="small" onClick={handleBulkUndo} loading={undoLoading}>
              ↩ Отменить
            </Button>
            <Button
              variant="outline"
              size="small"
              onClick={() => setUndoAvailable(false)}
              disabled={undoLoading}
            >
              Скрыть
            </Button>
          </div>
        </div>
      )}

      {/* ==================== Панель массовых действий ==================== */}
      {selected.length > 0 && (
        <div
          className="products-toolbar"
          style={{
            display: 'flex',
            gap: '0.5rem',
            alignItems: 'center',
            marginBottom: '0.75rem',
            flexWrap: 'wrap',
          }}
        >
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            Выбрано: <strong>{selected.length}</strong>
          </span>
          <Button variant="secondary" size="small" onClick={() => setShowBulkUpdate(true)}>
            <Icon name="edit" size={15} /> Обновить цену/бренд
          </Button>
          {onMigrate && (
            <Button
              variant="secondary"
              size="small"
              onClick={handleMigrateSelected}
              title={
                selBlockingTotal > 0
                  ? `⚠️ В ${selBlockingTotal} товарах есть блокирующие пропуски — миграция может завершиться с ошибками`
                  : 'Запустить миграцию выделенных товаров'
              }
            >
              <Icon name="migrate" size={15} /> Мигрировать выбранные
              {selBlockingTotal > 0 && (
                <span
                  style={{
                    marginLeft: '0.4rem',
                    padding: '0 0.4rem',
                    background: 'var(--danger, #ef4444)',
                    color: '#fff',
                    borderRadius: '999px',
                    fontSize: '0.7rem',
                    fontWeight: 700,
                  }}
                >
                  ⚠ {selBlockingTotal}
                </span>
              )}
            </Button>
          )}
          {/* ✅ Кнопка дозаполнения ТОЛЬКО выделенных (независимо от баннера) */}
          {selFillableTotal > 0 && (
            <Button
              variant="outline"
              size="small"
              onClick={() => handleApplyDefaults('selected')}
              loading={applyLoading}
              title="Дозаполнит пустые поля (НДС, ТН ВЭД, ОВХ, вес) из дефолтов только у выделенных товаров"
            >
              <Icon name="edit" size={15} /> Заполнить пропуски выделенных ({selFillableTotal})
            </Button>
          )}
          {/* ✅ v4: массовый подбор ТН ВЭД для выделенных */}
          <Button
            variant="secondary"
            size="small"
            onClick={() => setShowTnved(true)}
            title="Подобрать код ТН ВЭД сразу всем выделенным (авто-подбор по названию или поиск по справочнику)"
          >
            <Icon name="search" size={15} /> Подобрать ТН ВЭД
          </Button>
          <Button variant="secondary" size="small" onClick={() => setDeleteMode('bulk')}>
            <Icon name="trash" size={15} /> Удалить выбранные
          </Button>
          <Button variant="outline" size="small" onClick={() => setSelected([])}>
            Сбросить
          </Button>
        </div>
      )}

      {/* ==================== Таблица ==================== */}
      {loading && !products.length ? (
        <div className="card">
          <div className="loading-spinner">
            <div className="spinner" />
            <p style={{ color: 'var(--text-secondary)' }}>Загрузка товаров...</p>
          </div>
        </div>
      ) : !products.length ? (
        <EmptyState
          icon={<Icon name="layers" size={56} />}
          title="Товаров пока нет"
          description="Импортируйте товары из файла или по API-ключу площадки-источника."
          actionLabel={onImport ? 'Импортировать' : undefined}
          onAction={onImport}
        />
      ) : (
        <ProductsTable
          products={products}
          selected={selected}
          onToggleOne={toggleOne}
          onToggleAll={toggleAll}
          onLogistics={onLogistics}
          onAttributes={onAttributes}
          onVariants={onVariants}
          onPhotos={onPhotos}
          onMigrate={onMigrate}
          onDelete={(id) => {
            setDeleteTargetId(id);
            setDeleteMode('single');
          }}
          resize={{ colStyle, Resizer }}
        />
      )}

      {/* ==================== Пагинация ==================== */}
      <Pagination
        total={total}
        skip={skip}
        limit={limit}
        page={page}
        pages={pages}
        onSkipChange={setSkip}
        onLimitChange={(n) => {
          setLimit(n);
          setSkip(0);
        }}
      />

      {/* ==================== Модалки ==================== */}
      {deleteMode && (
        <DeleteConfirmModal
          mode={deleteMode}
          count={deleteMode === 'bulk' ? selected.length : 1}
          isAdmin={isAdmin}
          loading={deleteLoading}
          onConfirm={handleDeleteConfirm}
          onClose={() => {
            setDeleteMode(null);
            setDeleteTargetId(null);
          }}
        />
      )}

      {showBulkUpdate && (
        <BulkUpdateModal
          selectedIds={selected}
          count={selected.length}
          loading={bulkLoading}
          onSubmit={handleBulkUpdate}
          onClose={() => setShowBulkUpdate(false)}
        />
      )}

      {/* ✅ v4: массовый подбор ТН ВЭД */}
      {showTnved && (
        <BatchTnvedModal
          isOpen
          selectedIds={selected}
          onClose={() => setShowTnved(false)}
          onSaved={async () => {
            setUndoAvailable(true);
            setSelected([]);
            await load();
            await loadGaps();
          }}
        />
      )}

      {showDefaults && (
        <DefaultsModal
          isOpen
          onClose={() => {
            setShowDefaults(false);
            loadGaps();
          }}
          onNotify={setMessage}
          productCategories={productCategories}
          specNames={specNames}
        />
      )}
    </>
  );
};

export default ProductsPage;
