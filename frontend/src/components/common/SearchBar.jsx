import React from 'react';
import Icon from '../icons';

const STATUS_OPTIONS = [
  { value: 'all', label: 'Все статусы' },
  { value: 'pending', label: 'Ожидают' },
  { value: 'processing', label: 'В работе' },
  { value: 'success', label: 'Успешно' },
  { value: 'error', label: 'Ошибка' },
];

const SORT_OPTIONS = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
  { value: 'name_asc', label: 'Название А→Я' },
  { value: 'name_desc', label: 'Название Я→А' },
  { value: 'price_asc', label: 'Цена: по возрастанию' },
  { value: 'price_desc', label: 'Цена: по убыванию' },
];

const SearchBar = ({ filters, updateFilters, sources = [] }) => (
  <div className="search-bar">
    {/* Поиск */}
    <div className="search-wrap">
      <Icon name="search" size={16} className="search-icon" />
      <input
        className="form-input search-input"
        placeholder="Поиск по названию, SKU, артикулу..."
        value={filters.search || ''}
        onChange={(e) => updateFilters({ search: e.target.value })}
      />
      {filters.search && (
        <button
          type="button"
          className="search-clear"
          title="Очистить"
          onClick={() => updateFilters({ search: '' })}
        >
          <Icon name="close" size={14} />
        </button>
      )}
    </div>

    {/* Статус */}
    <select
      className="form-input select-small"
      value={filters.status || 'all'}
      onChange={(e) => updateFilters({ status: e.target.value })}
    >
      {STATUS_OPTIONS.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>

    {/* Источник (появляется, когда есть товары) */}
    {sources.length > 0 && (
      <select
        className="form-input select-small"
        value={filters.source || 'all'}
        onChange={(e) => updateFilters({ source: e.target.value })}
      >
        <option value="all">Все источники</option>
        {sources.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
    )}

    {/* Сортировка */}
    <select
      className="form-input select-small"
      value={filters.sort || 'newest'}
      onChange={(e) => updateFilters({ sort: e.target.value })}
    >
      {SORT_OPTIONS.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  </div>
);

export default SearchBar;