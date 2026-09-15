import React from 'react';
import ProductRow from './ProductRow';
import { detectPlatform } from '../../utils/platformUtils';

const ProductTable = ({ 
  products, 
  selectedIds, 
  isMigratingProductId,
  loading,
  availableForBatch,
  onSelect,
  onSelectAll,
  onMigrate 
}) => {
  if (products.length === 0) {
    return (
      <div className="table-container">
        <h2>Список товаров</h2>
        <p className="empty-state">
          Нет товаров. Нажмите "Импортировать товары" для начала.
        </p>
      </div>
    );
  }

  return (
    <div className="table-container">
      <h2>Список товаров</h2>
      <table>
        <thead>
          <tr>
            <th style={{ width: '40px' }}>
              <input
                type="checkbox"
                checked={selectedIds.length === availableForBatch && availableForBatch > 0}
                onChange={onSelectAll}
                className="checkbox-input"
              />
            </th>
            <th>ID</th>
            <th>Название</th>
            <th>Источник</th>
            <th>Цена</th>
            <th>Фото</th>
            <th>Статус</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => (
            <ProductRow
              key={product.id}
              product={product}
              isSelected={selectedIds.includes(product.id)}
              isMigrating={isMigratingProductId === product.id}
              loading={loading}
              onSelect={onSelect}
              onMigrate={onMigrate}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ProductTable;