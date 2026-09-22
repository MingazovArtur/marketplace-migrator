import React, { useMemo, useState, useEffect, useCallback } from 'react';
import Button from '../common/Button';
import Icon from '../icons';

const STATUS_BADGE = {
  pending: { label: 'Ожидает', cls: 'badge-pending' },
  processing: { label: 'В работе', cls: 'badge-processing' },
  success: { label: 'Успешно', cls: 'badge-success' },
  error: { label: 'Ошибка', cls: 'badge-error' },
};

/* ✅ Ширины по умолчанию, подобранные под наполнение. */
const DEFAULT_WIDTHS = {
  check: 44,
  name: 340,
  price: 110,
  source: 160,
  attrs: 220,
  status: 110,
  actions: 280,   // ✅ расширено с 250 до 280 — добавилась кнопка "Логистика"
};

const WIDTHS_KEY = 'product_table_widths_v3';   // ✅ v3: сбрасывает ширины с v2

/* ✅ Проверка готовности товара к экспорту (требования Ozon) */
const getExportReadiness = (product) => {
  const hasBarcode = !!product.barcode;
  const hasDimensions = !!(
    product.package_weight_grams &&
    product.package_width_mm &&
    product.package_height_mm &&
    product.package_length_mm
  );
  const hasVat = !!product.vat_rate;
  const filled = [hasBarcode, hasDimensions, hasVat].filter(Boolean).length;
  return {
    ready: filled === 3,
    filled,
    missing: {
      barcode: !hasBarcode,
      dimensions: !hasDimensions,
      vat: !hasVat,
    },
  };
};

const ProductTable = ({
  products,
  selectedIds,
  isMigratingProductId,
  loading,
  availableForBatch,
  onSelect,
  onSelectAll,
  onMigrate,
  onEditAttributes,
  onEditVariants,
  onEditPhotos,
  onEditLogistics,   // ✅ новый проп
  hasActiveFilters = false,
  onResetFilters = null,
}) => {
  const allSelected = availableForBatch > 0 && selectedIds.length === availableForBatch;

  /* ==================== Resize столбцов ==================== */
  const [widths, setWidths] = useState(() => {
    try {
      const saved = localStorage.getItem(WIDTHS_KEY);
      if (saved) return { ...DEFAULT_WIDTHS, ...JSON.parse(saved) };
    } catch (e) { /* ignore */ }
    return DEFAULT_WIDTHS;
  });

  useEffect(() => {
    try {
      localStorage.setItem(WIDTHS_KEY, JSON.stringify(widths));
    } catch (e) { /* ignore */ }
  }, [widths]);

  const startResize = useCallback((e, key) => {
    e.preventDefault();
    e.stopPropagation();
    const th = e.currentTarget.closest('th');
    const startX = e.pageX;
    const startWidth = th.getBoundingClientRect().width;

    const onMove = (ev) => {
      const delta = ev.pageX - startX;
      const newWidth = Math.max(60, Math.round(startWidth + delta));
      setWidths((prev) => ({ ...prev, [key]: newWidth }));
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
    };
    document.body.style.cursor = 'col-resize';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, []);

  const resetColumn = useCallback((key) => {
    setWidths((prev) => {
      const next = { ...prev };
      if (key in DEFAULT_WIDTHS) next[key] = DEFAULT_WIDTHS[key];
      else delete next[key];
      return next;
    });
  }, []);

  const colStyle = (key) =>
    widths[key] ? { width: widths[key], minWidth: widths[key], maxWidth: widths[key] } : undefined;

  const Resizer = ({ colKey }) => (
    <span
      className="col-resizer"
      onMouseDown={(e) => startResize(e, colKey)}
      onDoubleClick={() => resetColumn(colKey)}
      title="Тяните для изменения ширины. Двойной клик — сброс."
    />
  );

  const emptyRows = useMemo(() => {
    if (products.length >= 10) return [];
    return Array.from({ length: 10 - products.length });
  }, [products.length]);

  if (loading) {
    return (
      <div className="card">
        <div className="loading-spinner">
          <div className="spinner" />
          <p style={{ color: 'var(--text-secondary)' }}>Загрузка товаров...</p>
        </div>
      </div>
    );
  }

  if (!products.length) {
    return (
      <div className="card">
        <div className="empty-state">
          <div
            className="empty-state-icon"
            style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-muted)' }}
          >
            <Icon name="products" size={56} />
          </div>
          <p className="empty-state-text">
            {hasActiveFilters
              ? 'По выбранным фильтрам ничего не найдено.'
              : 'Нет товаров для отображения. Импортируйте товары, чтобы начать миграцию.'}
          </p>
          {hasActiveFilters && typeof onResetFilters === 'function' && (
            <Button variant="secondary" onClick={onResetFilters}>
              Сбросить фильтры
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div data-onboarding="products-table" className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div className="table-scroll">
        <table className="product-table">
          <thead>
            <tr>
              <th style={colStyle('check')}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onSelectAll}
                  disabled={availableForBatch === 0}
                  title="Выбрать все доступные для переноса"
                />
                <Resizer colKey="check" />
              </th>
              <th style={colStyle('name')}>
                Название
                <Resizer colKey="name" />
              </th>
              <th style={colStyle('price')}>
                Цена
                <Resizer colKey="price" />
              </th>
              <th style={colStyle('source')}>
                Источник
                <Resizer colKey="source" />
              </th>
              <th style={colStyle('attrs')}>
                Характеристики
                <Resizer colKey="attrs" />
              </th>
              <th style={colStyle('status')}>
                Статус
                <Resizer colKey="status" />
              </th>
              <th style={{ ...colStyle('actions'), textAlign: 'right' }}>
                Действия
              </th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => {
              const badge = STATUS_BADGE[product.status] || STATUS_BADGE.pending;
              const isSelected = selectedIds.includes(product.id);
              const isProcessing = isMigratingProductId === product.id;
              const canSelect = product.status !== 'success' && product.status !== 'processing';
              const attrs = product.attributes || [];
              const variants = product.variants || [];
              const photos = product.photos || [];

              // ✅ Индикатор готовности к экспорту
              const readiness = getExportReadiness(product);
              const missingLabels = [];
              if (readiness.missing.barcode) missingLabels.push('штрихкод');
              if (readiness.missing.dimensions) missingLabels.push('габариты упаковки');
              if (readiness.missing.vat) missingLabels.push('ставка НДС');

              const logisticsTitle = readiness.ready
                ? `Логистика: штрихкод, габариты, НДС — заполнено (${readiness.filled}/3)`
                : `Логистика: не заполнено: ${missingLabels.join(', ')} (${readiness.filled}/3)`;

              return (
                <tr key={product.id} className={isSelected ? 'selected' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onSelect(product.id)}
                      disabled={!canSelect}
                      title={!canSelect ? 'Товар уже мигрирован или в работе' : 'Выбрать товар'}
                    />
                  </td>
                  <td>
                    <div className="product-name" title={product.name}>{product.name}</div>
                    <div className="product-sub">
                      {product.sku && <>арт: {product.sku}</>}
                      {product.sku && product.brand && <> · </>}
                      {product.brand && <>{product.brand}</>}
                      {product.sku_count > 1 && <> · SKU: {product.sku_count}</>}
                    </div>
                  </td>
                  <td className="price-cell">
                    {product.price
                      ? `${Number(product.price).toLocaleString('ru-RU')} ₽`
                      : <span className="price-missing">не задана</span>}
                  </td>
                  <td>
                    <span className="source-badge" title={product.source}>{product.source}</span>
                  </td>
                  <td>
                    {attrs.length === 0 ? (
                      <span className="cell-muted">Не указаны</span>
                    ) : (
                      <div className="attributes-preview">
                        {attrs.slice(0, 2).map((attr, i) => (
                          <span key={attr.id ?? i} className="attr-chip" title={`${attr.name}: ${attr.value}`}>
                            {attr.name}: {attr.value}
                          </span>
                        ))}
                        {attrs.length > 2 && (
                          <span
                            className="attr-chip more"
                            title={attrs.slice(2).map(a => `${a.name}: ${a.value}`).join('\n')}
                          >
                            +{attrs.length - 2}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className={`badge ${badge.cls}`}>
                      {isProcessing ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                          <div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
                          В работе
                        </span>
                      ) : badge.label}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="row-actions">
                      <Button
                        variant="secondary"
                        size="small"
                        title="Фото товара"
                        onClick={() => onEditPhotos && onEditPhotos(product)}
                      >
                        <Icon name="photo" size={15} />
                        {photos.length > 0 && <span className="btn-count">{photos.length}</span>}
                      </Button>
                      <Button
                        variant="secondary"
                        size="small"
                        title="Характеристики"
                        onClick={() => onEditAttributes && onEditAttributes(product)}
                      >
                        <Icon name="tag" size={15} />
                      </Button>
                      <Button
                        variant="secondary"
                        size="small"
                        title="Вариации (SKU)"
                        onClick={() => onEditVariants && onEditVariants(product)}
                      >
                        <Icon name="variants" size={15} />
                        {variants.length > 0 && <span className="btn-count">{variants.length}</span>}
                      </Button>

                      {/* ✅ Кнопка "Логистика" с индикатором готовности */}
                      <Button
                        variant="secondary"
                        size="small"
                        title={logisticsTitle}
                        onClick={() => onEditLogistics && onEditLogistics(product)}
                      >
                        <Icon name="box" size={15} />
                        <span
                          className={`btn-count ${readiness.ready ? 'ready' : 'partial'}`}
                          title={readiness.ready ? 'Готов к экспорту' : 'Требует заполнения'}
                        >
                          {readiness.filled}/3
                        </span>
                      </Button>

                      <Button
                        size="small"
                        title="Перенести на площадку"
                        onClick={() => onMigrate(product.id)}
                        disabled={
                          product.status === 'processing' ||
                          product.status === 'success' ||
                          isProcessing
                        }
                        loading={isProcessing}
                      >
                        <Icon name="migrate" size={15} /> Мигрировать
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {emptyRows.map((_, i) => (
              <tr key={`empty-${i}`} className="empty-row">
                <td colSpan={7} style={{ height: 48, opacity: 0 }}>&nbsp;</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ProductTable;