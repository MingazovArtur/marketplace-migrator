import React, { useState, useEffect } from 'react';

const SearchBar = ({ filters, updateFilters }) => {
  const [searchInput, setSearchInput] = useState(filters.search || '');

  // Debounce для поиска
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== filters.search) {
        updateFilters({ search: searchInput, skip: 0 });
      }
    }, 300);
    
    return () => clearTimeout(timer);
  }, [searchInput, filters.search, updateFilters]);

  return (
    <div className="search-bar">
      <input
        type="text"
        placeholder="🔍 Поиск по названию..."
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
        className="search-input"
      />
      
      <select
        value={filters.status}
        onChange={(e) => updateFilters({ status: e.target.value, skip: 0 })}
        className="filter-select"
      >
        <option value="">Все статусы</option>
        <option value="pending">Ожидает</option>
        <option value="processing">В процессе</option>
        <option value="success">Успешно</option>
        <option value="error">Ошибка</option>
      </select>

      <select
        value={filters.source}
        onChange={(e) => updateFilters({ source: e.target.value, skip: 0 })}
        className="filter-select"
      >
        <option value="">Все источники</option>
        <option value="ozon">Ozon</option>
        <option value="wildberries">Wildberries</option>
        <option value="yandex">Яндекс Маркет</option>
      </select>

      <select
        value={`${filters.sort_by}-${filters.sort_order}`}
        onChange={(e) => {
          const [sort_by, sort_order] = e.target.value.split('-');
          updateFilters({ sort_by, sort_order, skip: 0 });
        }}
        className="filter-select"
      >
        <option value="created_at-desc">Сначала новые</option>
        <option value="created_at-asc">Сначала старые</option>
        <option value="price-desc">По цене (убывание)</option>
        <option value="price-asc">По цене (возрастание)</option>
        <option value="name-asc">По названию (А-Я)</option>
        <option value="name-desc">По названию (Я-А)</option>
      </select>
    </div>
  );
};

export default SearchBar;