import React, { useMemo } from 'react';
import Button from '../common/Button';

const STATUS_BADGE = {
  pending: { label: 'Ожидает', cls: 'badge-pending' },
  processing: { label: 'В работе', cls: 'badge-processing' },
  success: { label: 'Успешно', cls: 'badge-success' },
  error: { label: 'Ошибка', cls: 'badge-error' },
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
}) => {
  const allSelected =
    availableForBatch > 0 && selectedIds.length === availableForBatch;

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
          <div className="empty-state-icon">📦</div>
          <p className="empty-state-text">
            Нет товаров для отображения. Импортируйте товары, чтобы начать миграцию.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th style={{ width: 48 }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onSelectAll}
                  disabled={availableForBatch === 0}
                  title="Выбрать все"
                />
              </th>
              <th>Название</th>
              <th style={{ width: 110 }}>Цена</th>
              <th style={{ width: 140 }}>Источник</th>
              <th style={{ width: 200 }}>Характеристики</th>
              <th style={{ width: 110 }}>Статус</th>
              <th style={{ width: 380, textAlign: 'right' }}>Действия</th>
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
                    <div className="product-name" title={product.name}>
                      {product.name}
                    </div>
                    <div className="product-sub">
                      {product.sku && <>SKU: {product.sku} · </>}
                      {product.brand && <>{product.brand}</>}
                    </div>
                  </td>
                  <td className="price-cell">
                    {product.price ? `${product.price.toLocaleString('ru-RU')} ₽` : '—'}
                  </td>
                  <td>
                    <span className="source-badge" title={product.source}>
                      {product.source}
                    </span>
                  </td>
                  <td>
                    {attrs.length === 0 ? (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                        Не указаны
                      </span>
                    ) : (
                      <div className="attributes-preview">
                        {attrs.slice(0, 2).map((attr, i) => (
                          <span key={i} className="attr-chip" title={`${attr.name}: ${attr.value}`}>
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
                      {isProcessing ? '⏳ В работе' : badge.label}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                      <Button
                        variant="secondary"
                        size="small"
                        onClick={() => onEditPhotos(product)}
                        title="Фото товара"
                      >
                        🖼 {(product.photos || []).length || ''}
                      </Button>
                      <Button
                        variant="secondary"
                        size="small"
                        onClick={() => onEditVariants(product)}
                        title="Редактировать вариации (SKU)"
                      >
                        📦 {variants.length || ''}
                      </Button>
                      <Button
                        variant="secondary"
                        size="small"
                        onClick={() => onEditAttributes(product)}
                        title="Редактировать характеристики"
                      >
                        🏷 Характеристики
                      </Button>
                      <Button
                        onClick={() => onMigrate(product.id)}
                        disabled={
                          product.status === 'processing' ||
                          product.status === 'success' ||
                          isProcessing
                        }
                        loading={isProcessing}
                        size="small"
                      >
                        🚀 Мигрировать
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {emptyRows.map((_, i) => (
              <tr key={`empty-${i}`}>
                <td colSpan={7} style={{ height: 48, opacity: 0 }}>
                  &nbsp;
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ProductTable;