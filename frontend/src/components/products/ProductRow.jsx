import React, { memo } from 'react';
import Badge from '../common/Badge';

const ProductRow = memo(({ 
  product, 
  isSelected, 
  isMigrating, 
  loading,
  onSelect,
  onMigrate 
}) => {
  const isMigratable = product.status !== 'success' && 
                       product.status !== 'processing' && 
                       !isMigrating;

  return (
    <tr className={isSelected ? 'row-selected' : ''}>
      <td>
        {isMigratable && (
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => onSelect(product.id)}
            className="checkbox-input"
          />
        )}
      </td>
      <td>{product.id}</td>
      <td className="product-name" title={product.name}>
        {product.name}
      </td>
      <td>{product.source}</td>
      <td>{product.price} ₽</td>
      <td>{product.photos_count} шт.</td>
      <td>
        {product.status === 'processing' || isMigrating ? (
          <span className="badge badge-processing"> В процессе</span>
        ) : (
          <Badge status={product.status} />
        )}
      </td>
      <td>
        {product.status === 'success' ? (
          <span className="badge badge-success">✅ Готово</span>
        ) : product.status === 'error' ? (
          <button
            className="btn btn-sm btn-primary"
            onClick={() => onMigrate(product.id)}
            disabled={loading}
          >
            🔄 Повторить
          </button>
        ) : (
          <button
            className="btn btn-sm btn-primary"
            onClick={() => onMigrate(product.id)}
            disabled={loading || isMigrating}
          >
            {isMigrating ? '...' : 'Перенести'}
          </button>
        )}
      </td>
    </tr>
  );
});

ProductRow.displayName = 'ProductRow';

export default ProductRow;