import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import EmptyState from '../components/common/EmptyState';
import DeleteConfirmModal from '../components/products/DeleteConfirmModal';
import DefaultsModal from '../components/products/DefaultsModal';
import { api } from '../api';

const STATUS_META = {
  pending: { label: 'Ожидает', cls: 'badge-pending' },
  processing: { label: 'В работе', cls: 'badge-processing' },
  success: { label: 'Успешно', cls: 'badge-success' },
  error: { label: 'Ошибка', cls: 'badge-error' },
};

const SORT_OPTIONS = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
  { value: 'name_asc', label: 'Название А→Я' },
  { value: 'name_desc', label: 'Название Я→А' },
  { value: 'price_asc', label: 'Цена ↑' },
  { value: 'price_desc', label: 'Цена ↓' },
];

const DEFAULT_WIDTHS = {
  check: 40,
  id: 60,
  name: 320,
  category: 220,
  price: 110,
  status: 110,
  actions: 160,
};

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];

const GAP_LABELS = {
  vat_rate: 'НДС, %',
  okpd_code: 'ТН ВЭД',
  package_weight_grams: 'Вес в упаковке, г',
  package_width_mm: 'Ширина, мм',
  package_height_mm: 'Высота, мм',
  package_length_mm: 'Длина, мм',
  price: 'Цена > 0',
  main_photo: 'Главное фото',
};

// ✅ Поля, которые БЛОКИРУЮТ миграцию (критические)
const BLOCKING_GAP_FIELDS = ['price', 'main_photo'];

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

  const [colWidths, setColWidths] = useState({});

  const [selected, setSelected] = useState([]);
  const [deleteMode, setDeleteMode] = useState(null);
  const [deleteTargetId, setDeleteTargetId] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const [showBulkUpdate, setShowBulkUpdate] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);

  const [showDefaults, setShowDefaults] = useState(false);
  const [gaps, setGaps] = useState(null);
  const [gapsLoading, setGapsLoading] = useState(false);
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
    setGapsLoading(true);
    try {
      const g = await api.getGaps('all');
      setGaps(g);
    } catch {
      setGaps(null);
    } finally {
      setGapsLoading(false);
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

  // ==================== Ресайз колонок ====================
  const resetCol = (key) => {
    setColWidths((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const startResize = useCallback(
    (key, e) => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.pageX;
      const th = e.target.closest('th');
      const startW = colWidths[key] || th?.offsetWidth || DEFAULT_WIDTHS[key] || 120;

      const onMove = (ev) => {
        const w = Math.max(60, startW + (ev.pageX - startX));
        setColWidths((prev) => ({ ...prev, [key]: w }));
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [colWidths]
  );

  const colStyle = (key) => ({ width: colWidths[key] || DEFAULT_WIDTHS[key] });

  const Resizer = ({ colKey }) => (
    <span
      className="col-resizer"
      onMouseDown={(e) => startResize(colKey, e)}
      onDoubleClick={(e) => {
        e.stopPropagation();
        resetCol(colKey);
      }}
      onClick={(e) => e.stopPropagation()}
      title="Тянуть — ширина, двойной клик — сброс"
    />
  );

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
        setMessage(
          `Удалено: ${r.deleted}${r.skipped ? `, пропущено (чужие): ${r.skipped}` : ''}`
        );
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

  // ==================== Массовое обновление ====================
  const handleBulkUpdate = async (payload) => {
    setBulkLoading(true);
    try {
      const r = await api.bulkUpdateProducts({ product_ids: selected, ...payload });
      setMessage(`Обновлено товаров: ${r.updated}`);
      setShowBulkUpdate(false);
      setSelected([]);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBulkLoading(false);
    }
  };

  // ==================== Дозаполнение пропусков ====================
  const handleApplyDefaults = async (mode = 'all') => {
    setApplyLoading(true);
    try {
      const r = await api.applyDefaults(mode === 'selected' ? { product_ids: selected } : 'all');
      const summary = Object.entries(r.fields || {})
        .map(([k, v]) => `${GAP_LABELS[k] || k}: ${v}`)
        .join(', ');
      setMessage(
        `Дозаполнено товаров: ${r.updated} из ${r.total}` + (summary ? ` (${summary})` : '')
      );
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
  const gapsTotal = gapEntries.reduce((acc, [, n]) => acc + n, 0);

  // ✅ Пропуски в ВЫДЕЛЕННЫХ товарах (для badge и confirm)
  const selectedGaps = useMemo(() => {
    if (selected.length === 0) return null;
    const selectedProducts = products.filter((p) => selected.includes(p.id));
    const gapsLocal = {};
    selectedProducts.forEach((p) => {
      const price = Number(p.price);
      if (!price || price <= 0 || isNaN(price)) gapsLocal.price = (gapsLocal.price || 0) + 1;
      if (!p.photos || p.photos.length === 0)
        gapsLocal.main_photo = (gapsLocal.main_photo || 0) + 1;
      [
        'vat_rate',
        'okpd_code',
        'package_weight_grams',
        'package_width_mm',
        'package_height_mm',
        'package_length_mm',
      ].forEach((f) => {
        if (p[f] === null || p[f] === undefined || p[f] === '' || p[f] === 0) {
          gapsLocal[f] = (gapsLocal[f] || 0) + 1;
        }
      });
    });
    return gapsLocal;
  }, [selected, products]);

  const selectedBlockingTotal = selectedGaps
    ? BLOCKING_GAP_FIELDS.reduce((acc, k) => acc + (selectedGaps[k] || 0), 0)
    : 0;
  const selectedFillableTotal = selectedGaps
    ? Object.entries(selectedGaps)
        .filter(([k]) => !BLOCKING_GAP_FIELDS.includes(k))
        .reduce((acc, [, n]) => acc + n, 0)
    : 0;

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
            <Button onClick={onImport}>
              <Icon name="import" size={16} /> Импорт
            </Button>
          )}
          {onExport && (
            <Button variant="secondary" onClick={onExport}>
              <Icon name="export" size={16} /> Выгрузка
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => setDeleteMode('all')}
            title={isAdmin ? 'Удалить все товары в системе' : 'Удалить все мои товары'}
          >
            <Icon name="trash" size={16} />{' '}
            {isAdmin ? 'Удалить все в системе' : 'Удалить все товары'}
          </Button>
          <Button variant="secondary" onClick={load} disabled={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
        </div>
      </header>

      {/* ==================== Баннер пропусков ==================== */}
      {gaps && gaps.total > 0 && gapEntries.length > 0 && (
        <div className="alert alert-error" style={{ marginBottom: '0.75rem' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.5rem',
            }}
          >
            <div>
              ❌ Пропуски обязательных полей у {gaps.total} товаров:{' '}
              <strong>
                {gapEntries.map(([k, n]) => `${GAP_LABELS[k] || k} — ${n}`).join('; ')}
              </strong>
              {selected.length > 0 && selectedBlockingTotal + selectedFillableTotal > 0 && (
                <span
                  style={{
                    display: 'block',
                    marginTop: '0.25rem',
                    fontSize: '0.85rem',
                    opacity: 0.9,
                  }}
                >
                  ↳ в выделенных ({selected.length}):{' '}
                  {Object.entries(selectedGaps || {})
                    .filter(([, n]) => n > 0)
                    .map(([k, n]) => `${GAP_LABELS[k] || k} — ${n}`)
                    .join('; ')}
                </span>
              )}
            </div>
            <Button size="small" onClick={() => handleApplyDefaults('all')} loading={applyLoading}>
              <Icon name="edit" size={15} /> Заполнить пропуски из дефолтов (все товары)
            </Button>
          </div>
          <p style={{ margin: '0.4rem 0 0', fontSize: '0.85rem', opacity: 0.9 }}>
            Значения берутся из <strong>Дефолтов экспорта</strong>: глобальных и по категориям. Один
            клик — и все товары получат НДС, ТН ВЭД, ОВХ и вес.
          </p>
        </div>
      )}

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

        <Button variant="secondary" onClick={() => setShowDefaults(true)}>
          <Icon name="settings" size={16} /> Дефолты
        </Button>
        {gapsTotal > 0 && (
          <Button
            variant="outline"
            onClick={() => handleApplyDefaults('all')}
            loading={applyLoading}
            title="Дозаполнит пустые НДС/ТН ВЭД/ОВХ/вес из дефолтов по всем товарам"
          >
            <Icon name="edit" size={16} /> Заполнить пропуски ({gapsTotal})
          </Button>
        )}
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
                selectedBlockingTotal > 0
                  ? `⚠️ В ${selectedBlockingTotal} товарах есть блокирующие пропуски — миграция может завершиться с ошибками`
                  : 'Запустить миграцию выделенных товаров'
              }
            >
              <Icon name="migrate" size={15} /> Мигрировать выбранные
              {selectedBlockingTotal > 0 && (
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
                  ⚠ {selectedBlockingTotal}
                </span>
              )}
            </Button>
          )}
          {/* ✅ Кнопка дозаполнения ТОЛЬКО выделенных (независимо от баннера) */}
          {selectedFillableTotal > 0 && (
            <Button
              variant="outline"
              size="small"
              onClick={() => handleApplyDefaults('selected')}
              loading={applyLoading}
              title="Дозаполнит пустые поля (НДС, ТН ВЭД, ОВХ, вес) из дефолтов только у выделенных товаров"
            >
              <Icon name="edit" size={15} /> Заполнить пропуски выделенных ({selectedFillableTotal})
            </Button>
          )}
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
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.85rem',
              tableLayout: 'fixed',
            }}
          >
            <thead style={{ background: 'var(--bg-secondary)' }}>
              <tr>
                <th className="th-resizable" style={{ padding: '0.6rem', ...colStyle('check') }}>
                  <input
                    type="checkbox"
                    checked={products.length > 0 && products.every((p) => selected.includes(p.id))}
                    onChange={toggleAll}
                  />
                  <Resizer colKey="check" />
                </th>
                <th
                  className="th-resizable"
                  style={{ textAlign: 'left', padding: '0.6rem', ...colStyle('id') }}
                >
                  ID <Resizer colKey="id" />
                </th>
                <th
                  className="th-resizable"
                  style={{ textAlign: 'left', padding: '0.6rem', ...colStyle('name') }}
                >
                  Товар <Resizer colKey="name" />
                </th>
                <th
                  className="th-resizable"
                  style={{ textAlign: 'left', padding: '0.6rem', ...colStyle('category') }}
                >
                  Категория → Ozon <Resizer colKey="category" />
                </th>
                <th
                  className="th-resizable"
                  style={{ textAlign: 'right', padding: '0.6rem', ...colStyle('price') }}
                >
                  Цена <Resizer colKey="price" />
                </th>
                <th
                  className="th-resizable"
                  style={{ textAlign: 'center', padding: '0.6rem', ...colStyle('status') }}
                >
                  Статус <Resizer colKey="status" />
                </th>
                <th
                  className="th-resizable"
                  style={{ textAlign: 'center', padding: '0.6rem', ...colStyle('actions') }}
                >
                  Действия <Resizer colKey="actions" />
                </th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => {
                const st = STATUS_META[p.status] || STATUS_META.pending;
                const price = Number(p.price);
                const priceBad = !price || price <= 0 || isNaN(price);
                const photoBad = !p.photos || p.photos.length === 0;
                const hasBlocking = priceBad || photoBad;
                return (
                  <tr key={p.id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                    <td style={{ padding: '0.6rem', overflow: 'hidden' }}>
                      <input
                        type="checkbox"
                        checked={selected.includes(p.id)}
                        onChange={() => toggleOne(p.id)}
                      />
                    </td>
                    <td
                      style={{
                        padding: '0.6rem',
                        color: 'var(--text-muted)',
                        fontFamily: 'monospace',
                        overflow: 'hidden',
                      }}
                    >
                      {p.id}
                    </td>
                    <td style={{ padding: '0.6rem', overflow: 'hidden' }}>
                      <div
                        style={{
                          fontWeight: 600,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                        title={p.name}
                      >
                        {p.name}
                      </div>
                      <div
                        style={{
                          color: 'var(--text-muted)',
                          fontSize: '0.75rem',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {p.sku || p.external_id || 'без артикула'} · {p.source}
                      </div>
                    </td>
                    <td
                      style={{
                        padding: '0.6rem',
                        color: 'var(--text-secondary)',
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {p.category || 'Не указана'}
                      </div>
                      {p.mapped_category && (
                        <div
                          style={{
                            fontSize: '0.75rem',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          → {p.mapped_category}
                        </div>
                      )}
                    </td>
                    <td
                      style={{
                        padding: '0.6rem',
                        textAlign: 'right',
                        fontWeight: 600,
                        overflow: 'hidden',
                        color: priceBad ? 'var(--danger, #ef4444)' : undefined,
                      }}
                      title={
                        priceBad
                          ? '❌ Цена не указана или = 0 — миграция будет отклонена'
                          : undefined
                      }
                    >
                      {priceBad ? '❌ —' : `${p.price} ₽`}
                    </td>
                    <td style={{ padding: '0.6rem', textAlign: 'center', overflow: 'hidden' }}>
                      <span className={`badge ${st.cls}`}>{st.label}</span>
                    </td>
                    <td style={{ padding: '0.6rem', overflow: 'hidden' }}>
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
                          gap: '0.25rem',
                        }}
                      >
                        {onLogistics && (
                          <Button
                            variant="secondary"
                            size="small"
                            title="Логистика"
                            onClick={() => {
                              console.log(
                                '📦 Открываем логистику для товара',
                                p.id,
                                'package_weight_grams:',
                                p.package_weight_grams
                              );
                              onLogistics(p);
                            }}
                          >
                            <Icon name="box" size={15} />
                          </Button>
                        )}
                        {onAttributes && (
                          <Button
                            variant="secondary"
                            size="small"
                            title="Характеристики"
                            onClick={() => onAttributes(p)}
                          >
                            <Icon name="tag" size={15} />
                          </Button>
                        )}
                        {onVariants && (
                          <Button
                            variant="secondary"
                            size="small"
                            title="Варианты"
                            onClick={() => onVariants(p)}
                          >
                            <Icon name="variants" size={15} />
                          </Button>
                        )}
                        {onPhotos && (
                          <Button
                            variant="secondary"
                            size="small"
                            title={
                              photoBad ? '❌ Фото отсутствует — миграция будет отклонена' : 'Фото'
                            }
                            onClick={() => onPhotos(p)}
                            style={
                              photoBad
                                ? { boxShadow: '0 0 0 2px var(--danger, #ef4444)' }
                                : undefined
                            }
                          >
                            <Icon name="photo" size={15} />
                          </Button>
                        )}
                        {onMigrate && (
                          <Button
                            variant="secondary"
                            size="small"
                            title={
                              hasBlocking ? '⚠️ Товар имеет блокирующие пропуски' : 'Мигрировать'
                            }
                            onClick={() => onMigrate(p)}
                            style={
                              hasBlocking
                                ? { boxShadow: '0 0 0 2px var(--warning, #f59e0b)' }
                                : undefined
                            }
                          >
                            <Icon name="migrate" size={15} />
                          </Button>
                        )}
                        <Button
                          variant="secondary"
                          size="small"
                          title="Удалить товар"
                          onClick={() => {
                            setDeleteTargetId(p.id);
                            setDeleteMode('single');
                          }}
                        >
                          <Icon name="trash" size={15} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ==================== Пагинация ==================== */}
      {total > 0 && (
        <div
          style={{
            display: 'flex',
            gap: '0.5rem',
            justifyContent: 'center',
            alignItems: 'center',
            marginTop: '0.75rem',
            flexWrap: 'wrap',
          }}
        >
          <Button
            variant="secondary"
            size="small"
            disabled={skip === 0}
            onClick={() => setSkip(0)}
            title="Первая страница"
          >
            « В начало
          </Button>
          <Button
            variant="secondary"
            size="small"
            disabled={skip === 0}
            onClick={() => setSkip(Math.max(0, skip - limit))}
          >
            ← Назад
          </Button>
          <span
            style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', padding: '0 0.25rem' }}
          >
            Стр. {page} из {pages} · всего {total}
          </span>
          <Button
            variant="secondary"
            size="small"
            disabled={skip + limit >= total}
            onClick={() => setSkip(skip + limit)}
          >
            Вперёд →
          </Button>
          <Button
            variant="secondary"
            size="small"
            disabled={skip + limit >= total}
            onClick={() => setSkip((pages - 1) * limit)}
            title="Последняя страница"
          >
            В конец »
          </Button>
          <select
            className="form-input"
            style={{
              width: 64,
              padding: '0.25rem 0.4rem',
              marginLeft: '0.5rem',
              textAlign: 'center',
              fontSize: '0.85rem',
            }}
            value={limit}
            onChange={(e) => {
              setLimit(Number(e.target.value));
              setSkip(0);
            }}
            title="Товаров на странице"
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      )}

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
          count={selected.length}
          loading={bulkLoading}
          onSubmit={handleBulkUpdate}
          onClose={() => setShowBulkUpdate(false)}
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

/* ========== Модалка массового обновления ========== */
const BulkUpdateModal = ({ count, loading, onSubmit, onClose }) => {
  const [pricePercent, setPricePercent] = useState('');
  const [brand, setBrand] = useState('');
  const [category, setCategory] = useState('');

  const canSubmit = pricePercent !== '' || brand.trim() || category.trim();

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="edit" size={20} /> Массовое обновление ({count})
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <label className="form-label">Наценка / скидка, %</label>
        <input
          className="form-input"
          type="number"
          value={pricePercent}
          onChange={(e) => setPricePercent(e.target.value)}
          placeholder="Например: 15 или -10"
          disabled={loading}
        />
        <p className="form-hint">Цена каждого товара будет умножена на (1 + %/100).</p>

        <label className="form-label">Бренд</label>
        <input
          className="form-input"
          type="text"
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
          placeholder="Оставьте пустым, чтобы не менять"
          disabled={loading}
        />

        <label className="form-label">Категория назначения</label>
        <input
          className="form-input"
          type="text"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="Например: Одежда / Футболка"
          disabled={loading}
        />

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Отмена
          </Button>
          <Button
            onClick={() =>
              onSubmit({
                price_percent: pricePercent === '' ? undefined : Number(pricePercent),
                brand: brand.trim() || undefined,
                category: category.trim() || undefined,
              })
            }
            disabled={loading || !canSubmit}
            loading={loading}
          >
            <Icon name="edit" size={16} /> Применить
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ProductsPage;