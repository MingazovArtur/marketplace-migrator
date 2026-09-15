import React from 'react';
import ProductRow from './ProductRow';

const ProductTable = ({ products, selectedIds, isMigratingProductId, loading, availableForBatch, onSelect, onSelectAll, onMigrate }) => {
  if (products.length === 0) {
    return (
      <div className="table-container">
        <div className="table-header">
          <h2 className="table-title">Список товаров</h2>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon">📦</div>
          <p className="empty-state-text">Нет товаров. Нажмите "Импортировать товары" для начала.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="table-container">
      <div className="table-header">
        <h2 className="table-title">Список товаров</h2>
        <div className="table-actions">
          <input
            type="checkbox"
            checked={selectedIds.length === availableForBatch && availableForBatch > 0}
            onChange={onSelectAll}
            className="checkbox-input"
          />
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th style={{ width: '40px' }}></th>
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
    </div>
  );
};

export default ProductTable;