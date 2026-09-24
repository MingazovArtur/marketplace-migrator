import React, { useState, useEffect, useCallback, useRef } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import EmptyState from '../components/common/EmptyState';
import DeleteConfirmModal from '../components/products/DeleteConfirmModal';
import { api } from '../api';

const STATUS_META = {
  pending:    { label: 'Ожидает',  cls: 'badge-pending' },
  processing: { label: 'В работе', cls: 'badge-processing' },
  success:    { label: 'Успешно',  cls: 'badge-success' },
  error:      { label: 'Ошибка',   cls: 'badge-error' },
};

const SORT_OPTIONS = [
  { value: 'newest',     label: 'Сначала новые' },
  { value: 'oldest',     label: 'Сначала старые' },
  { value: 'name_asc',   label: 'Название А→Я' },
  { value: 'name_desc',  label: 'Название Я→А' },
  { value: 'price_asc',  label: 'Цена ↑' },
  { value: 'price_desc', label: 'Цена ↓' },
];

const DEFAULT_WIDTHS = {
  check: 40, id: 60, name: 320, category: 220, price: 110, status: 110, actions: 160,
};

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];

const ProductsPage = ({
  isAdmin = false,
  onMigrate, onLogistics, onAttributes, onVariants, onPhotos, onExport, onImport,
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

  // ==================== Загрузка ====================
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const d = await api.getProducts({
        search: search || undefined,
        status, source: 'all', sort, skip, limit,
      });
      setProducts(d.products || []);
      setTotal(d.total ?? (d.products || []).length);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [search, status, sort, skip, limit]);

  useEffect(() => { load(); }, [load]);

  // ==================== Ресайз колонок ====================
  const resetCol = (key) => {
    setColWidths((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const startResize = useCallback((key, e) => {
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
  }, [colWidths]);

  const colStyle = (key) => ({ width: colWidths[key] || DEFAULT_WIDTHS[key] });

  const Resizer = ({ colKey }) => (
    <span
      className="col-resizer"
      onMouseDown={(e) => startResize(colKey, e)}
      onDoubleClick={(e) => { e.stopPropagation(); resetCol(colKey); }}
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
        setMessage(`🗑 Удалено товаров: ${r.deleted}`);
        setSelected([]);
      } else if (deleteMode === 'bulk') {
        const r = await api.bulkDeleteProducts(selected);
        setMessage(`🗑 Удалено: ${r.deleted}${r.skipped ? `, пропущено (чужие): ${r.skipped}` : ''}`);
        setSelected([]);
      } else {
        await api.deleteProduct(deleteTargetId);
        setMessage('🗑 Товар удалён');
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
      setMessage(`✏️ Обновлено товаров: ${r.updated}`);
      setShowBulkUpdate(false);
      setSelected([]);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBulkLoading(false);
    }
  };

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
            <Icon name="trash" size={16} /> {isAdmin ? 'Удалить все в системе' : 'Удалить все товары'}
          </Button>
          <Button variant="secondary" onClick={load} disabled={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
        </div>
      </header>

      {/* ==================== Фильтры + сброс ширины колонок ==================== */}
      <div className="products-toolbar" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
        <input
          className="form-input"
          placeholder="Поиск: название, SKU, артикул…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setSkip(0); }}
          style={{ flex: 1, minWidth: 200 }}
        />
        <select className="form-input" value={status} onChange={(e) => { setStatus(e.target.value); setSkip(0); }} style={{ width: 'auto' }}>
          <option value="all">Все статусы</option>
          <option value="pending">Ожидает</option>
          <option value="processing">В работе</option>
          <option value="success">Успешно</option>
          <option value="error">Ошибка</option>
        </select>
        <select className="form-input" value={sort} onChange={(e) => { setSort(e.target.value); setSkip(0); }} style={{ width: 'auto' }}>
          {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
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
      </div>

      {error && <div className="alert alert-error"><div>{error}</div></div>}
      {message && <div className="alert alert-success"><div>{message}</div></div>}

      {/* ==================== Панель массовых действий ==================== */}
      {selected.length > 0 && (
        <div className="products-toolbar" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            Выбрано: <strong>{selected.length}</strong>
          </span>
          <Button variant="secondary" size="small" onClick={() => setShowBulkUpdate(true)}>
            <Icon name="edit" size={15} /> Обновить цену/бренд
          </Button>
          {onMigrate && (
            <Button variant="secondary" size="small" onClick={() => onMigrate(selected)}>
              <Icon name="migrate" size={15} /> Мигрировать выбранные
            </Button>
          )}
          <Button variant="secondary" size="small" onClick={() => setDeleteMode('bulk')}>
            <Icon name="trash" size={15} /> Удалить выбранные
          </Button>
          <Button variant="outline" size="small" onClick={() => setSelected([])}>Сбросить</Button>
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
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', tableLayout: 'fixed' }}>
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
                <th className="th-resizable" style={{ textAlign: 'left', padding: '0.6rem', ...colStyle('id') }}>
                  ID <Resizer colKey="id" />
                </th>
                <th className="th-resizable" style={{ textAlign: 'left', padding: '0.6rem', ...colStyle('name') }}>
                  Товар <Resizer colKey="name" />
                </th>
                <th className="th-resizable" style={{ textAlign: 'left', padding: '0.6rem', ...colStyle('category') }}>
                  Категория → Ozon <Resizer colKey="category" />
                </th>
                <th className="th-resizable" style={{ textAlign: 'right', padding: '0.6rem', ...colStyle('price') }}>
                  Цена <Resizer colKey="price" />
                </th>
                <th className="th-resizable" style={{ textAlign: 'center', padding: '0.6rem', ...colStyle('status') }}>
                  Статус <Resizer colKey="status" />
                </th>
                <th className="th-resizable" style={{ textAlign: 'center', padding: '0.6rem', ...colStyle('actions') }}>
                  Действия <Resizer colKey="actions" />
                </th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => {
                const st = STATUS_META[p.status] || STATUS_META.pending;
                return (
                  /* ✅ СТРОГО 7 ЯЧЕЕК в порядке шапки:
                     1 checkbox | 2 ID | 3 Товар | 4 Категория | 5 Цена | 6 Статус | 7 Действия */
                  <tr key={p.id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                    {/* 1 */}
                    <td style={{ padding: '0.6rem', overflow: 'hidden' }}>
                      <input type="checkbox" checked={selected.includes(p.id)} onChange={() => toggleOne(p.id)} />
                    </td>
                    {/* 2 */}
                    <td style={{ padding: '0.6rem', color: 'var(--text-muted)', fontFamily: 'monospace', overflow: 'hidden' }}>
                      {p.id}
                    </td>
                    {/* 3 */}
                    <td style={{ padding: '0.6rem', overflow: 'hidden' }}>
                      <div style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={p.name}>
                        {p.name}
                      </div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {p.sku || p.external_id || 'без артикула'} · {p.source}
                      </div>
                    </td>
                    {/* 4 */}
                    <td style={{ padding: '0.6rem', color: 'var(--text-secondary)', overflow: 'hidden' }}>
                      <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.category || 'Не указана'}</div>
                      {p.mapped_category && (
                        <div style={{ fontSize: '0.75rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>→ {p.mapped_category}</div>
                      )}
                    </td>
                    {/* 5 */}
                    <td style={{ padding: '0.6rem', textAlign: 'right', fontWeight: 600, overflow: 'hidden' }}>
                      {p.price != null ? `${p.price} ₽` : '—'}
                    </td>
                    {/* 6 */}
                    <td style={{ padding: '0.6rem', textAlign: 'center', overflow: 'hidden' }}>
                      <span className={`badge ${st.cls}`}>{st.label}</span>
                    </td>
                    {/* 7 — ДЕЙСТВИЯ: grid 3×2 ТОЛЬКО внутри этой ячейки */}
                    <td style={{ padding: '0.6rem', overflow: 'hidden' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.25rem' }}>
                        {onLogistics && (
                          <Button variant="secondary" size="small" title="Логистика" onClick={() => onLogistics(p)}>
                            <Icon name="box" size={15} />
                          </Button>
                        )}
                        {onAttributes && (
                          <Button variant="secondary" size="small" title="Характеристики" onClick={() => onAttributes(p)}>
                            <Icon name="tag" size={15} />
                          </Button>
                        )}
                        {onVariants && (
                          <Button variant="secondary" size="small" title="Варианты" onClick={() => onVariants(p)}>
                            <Icon name="variants" size={15} />
                          </Button>
                        )}
                        {onPhotos && (
                          <Button variant="secondary" size="small" title="Фото" onClick={() => onPhotos(p)}>
                            <Icon name="photo" size={15} />
                          </Button>
                        )}
                        {onMigrate && (
                          <Button variant="secondary" size="small" title="Мигрировать" onClick={() => onMigrate(p)}>
                            <Icon name="migrate" size={15} />
                          </Button>
                        )}
                        <Button
                          variant="secondary"
                          size="small"
                          title="Удалить товар"
                          onClick={() => { setDeleteTargetId(p.id); setDeleteMode('single'); }}
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

      {/* ==================== Пагинация: начало/конец + компактный селект лимита ==================== */}
      {total > 0 && (
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', alignItems: 'center', marginTop: '0.75rem', flexWrap: 'wrap' }}>
          <Button variant="secondary" size="small" disabled={skip === 0} onClick={() => setSkip(0)} title="Первая страница">
            « В начало
          </Button>
          <Button variant="secondary" size="small" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - limit))}>
            ← Назад
          </Button>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', padding: '0 0.25rem' }}>
            Стр. {page} из {pages} · всего {total}
          </span>
          <Button variant="secondary" size="small" disabled={skip + limit >= total} onClick={() => setSkip(skip + limit)}>
            Вперёд →
          </Button>
          <Button variant="secondary" size="small" disabled={skip + limit >= total} onClick={() => setSkip((pages - 1) * limit)} title="Последняя страница">
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
            onChange={(e) => { setLimit(Number(e.target.value)); setSkip(0); }}
            title="Товаров на странице"
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
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
          onClose={() => { setDeleteMode(null); setDeleteTargetId(null); }}
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
          <h2 className="modal-title">Массовое обновление ({count})</h2>
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
          <Button variant="outline" onClick={onClose} disabled={loading}>Отмена</Button>
          <Button
            onClick={() => onSubmit({
              price_percent: pricePercent === '' ? undefined : Number(pricePercent),
              brand: brand.trim() || undefined,
              category: category.trim() || undefined,
            })}
            disabled={loading || !canSubmit}
            loading={loading}
          >
            Применить
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ProductsPage;