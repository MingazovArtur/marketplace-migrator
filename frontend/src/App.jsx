import React, { useState } from 'react';
import './App.css';

function App() {
  // Имитация данных (позже заменим на запросы к вашему Python-бэкенду)
  const [stats, setStats] = useState({ total: 12, pending: 5, success: 6, error: 1 });
  const [products, setProducts] = useState([
    { id: 1, name: 'Швабра с отжимом, 10л', source: 'KazanExpress', price: 899, status: 'pending' },
    { id: 2, name: 'Набор пластиковых мисок', source: 'KazanExpress', price: 450, status: 'success' },
    { id: 3, name: 'Ведро для швабры', source: 'KazanExpress', price: 320, status: 'error' },
  ]);

  const getStatusBadge = (status) => {
    const styles = {
      pending: 'badge-pending',
      success: 'badge-success',
      error: 'badge-error',
      processing: 'badge-processing'
    };
    const labels = {
      pending: 'Ожидает',
      success: 'Успешно',
      error: 'Ошибка',
      processing: 'В процессе'
    };
    return <span className={`badge ${styles[status]}`}>{labels[status]}</span>;
  };

  return (
    <div className="app-container">
      {/* Шапка */}
      <header className="header">
        <h1>🔄 Marketplace Migrator</h1>
        <p>Перенос карточек товаров между маркетплейсами</p>
      </header>

      {/* Статистика */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Всего товаров</div>
          <div className="stat-value">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Ожидают миграции</div>
          <div className="stat-value" style={{ color: '#f59e0b' }}>{stats.pending}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Успешно перенесено</div>
          <div className="stat-value" style={{ color: '#10b981' }}>{stats.success}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Ошибки</div>
          <div className="stat-value" style={{ color: '#ef4444' }}>{stats.error}</div>
        </div>
      </div>

      {/* Кнопки действий */}
      <div className="actions-panel">
        <button className="btn btn-primary" onClick={() => alert('Здесь будет вызов API для импорта')}>
          📥 Импортировать товары
        </button>
        <button className="btn btn-secondary" onClick={() => alert('Здесь будет запуск массовой миграции')}>
          🔄 Запустить миграцию
        </button>
        <button className="btn btn-outline" onClick={() => alert('Настройки API ключей')}>
          ⚙️ Настройки API
        </button>
      </div>

      {/* Таблица товаров */}
      <div className="table-container">
        <h2>Список товаров</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Источник</th>
              <th>Цена</th>
              <th>Статус</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => (
              <tr key={product.id}>
                <td>{product.id}</td>
                <td className="product-name">{product.name}</td>
                <td>{product.source}</td>
                <td>{product.price} ₽</td>
                <td>{getStatusBadge(product.status)}</td>
                <td>
                  <button 
                    className="btn btn-sm btn-primary"
                    onClick={() => alert(`Миграция товара #${product.id} запущена!`)}
                  >
                    Перенести
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default App;