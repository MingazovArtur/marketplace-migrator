import React from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { STATUS_META, fmtPrice } from './tableUtils';

/* Таблица товаров (Р4: вынесено из ProductsPage.jsx без изменения разметки).
 * Ресайз колонок приходит пропсом resize = { colStyle, Resizer } из хука useColumnResize. */
const ProductsTable = ({
  products,
  selected,
  onToggleOne,
  onToggleAll,
  onLogistics,
  onAttributes,
  onVariants,
  onPhotos,
  onMigrate,
  onDelete,
  resize,
}) => {
  const { colStyle, Resizer } = resize;

  return (
    <div
      className="card"
      style={{ padding: 0, overflowX: 'auto' }}
      data-onboarding="products-table"
    >
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
                onChange={onToggleAll}
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
                    onChange={() => onToggleOne(p.id)}
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
                    priceBad ? '❌ Цена не указана или = 0 — миграция будет отклонена' : undefined
                  }
                >
                  {priceBad ? '❌ —' : `${fmtPrice(p.price)} ₽`}
                </td>
                <td style={{ padding: '0.6rem', textAlign: 'center', overflow: 'hidden' }}>
                  <span className={`badge ${st.cls}`}>{st.label}</span>
                </td>
                <td style={{ padding: '0.45rem 0.6rem', overflow: 'hidden' }}>
                  {/* Компактные иконки-кнопки: раньше у каждой было 16px
                      горизонтального паддинга и кнопка была втрое шире иконки */}
                  <div className="row-actions">
                    {onLogistics && (
                      <Button
                        variant="secondary"
                        size="small"
                        className="btn-icon"
                        title="Логистика: вес, габариты, НДС, ТН ВЭД"
                        onClick={() => onLogistics(p)}
                      >
                        <Icon name="box" size={19} />
                      </Button>
                    )}
                    {onAttributes && (
                      <Button
                        variant="secondary"
                        size="small"
                        className="btn-icon"
                        title="Характеристики"
                        onClick={() => onAttributes(p)}
                      >
                        <Icon name="tag" size={19} />
                      </Button>
                    )}
                    {onVariants && (
                      <Button
                        variant="secondary"
                        size="small"
                        className="btn-icon"
                        title="Варианты (SKU)"
                        onClick={() => onVariants(p)}
                      >
                        <Icon name="variants" size={19} />
                      </Button>
                    )}
                    {onPhotos && (
                      <Button
                        variant="secondary"
                        size="small"
                        className="btn-icon"
                        title={photoBad ? '❌ Фото отсутствует — миграция будет отклонена' : 'Фото'}
                        onClick={() => onPhotos(p)}
                        style={
                          photoBad ? { boxShadow: '0 0 0 2px var(--danger, #ef4444)' } : undefined
                        }
                      >
                        <Icon name="photo" size={19} />
                      </Button>
                    )}
                    {onMigrate && (
                      <Button
                        variant="secondary"
                        size="small"
                        className="btn-icon"
                        data-onboarding="migrate-btn"
                        title={hasBlocking ? '⚠️ Товар имеет блокирующие пропуски' : 'Мигрировать'}
                        onClick={() => onMigrate(p)}
                        style={
                          hasBlocking
                            ? { boxShadow: '0 0 0 2px var(--warning, #f59e0b)' }
                            : undefined
                        }
                      >
                        <Icon name="migrate" size={19} />
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      size="small"
                      className="btn-icon"
                      title="Удалить товар"
                      onClick={() => onDelete(p.id)}
                    >
                      <Icon name="trash" size={19} />
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default ProductsTable;
