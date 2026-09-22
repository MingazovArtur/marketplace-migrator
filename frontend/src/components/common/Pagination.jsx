import React from 'react';

const Pagination = ({ total, skip, limit, onPageChange, onLimitChange }) => {
  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  if (totalPages <= 1) return null;

  const pages = [];
  for (let i = 1; i <= totalPages; i++) {
    pages.push(i);
  }

  return (
    <div className="pagination">
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className="pagination-btn"
      >
        ← Назад
      </button>

      {pages.map(page => (
        <button
          key={page}
          onClick={() => onPageChange(page)}
          className={`pagination-btn ${page === currentPage ? 'active' : ''}`}
        >
          {page}
        </button>
      ))}

      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="pagination-btn"
      >
        Вперёд →
      </button>

      <span className="pagination-info">
        Страница {currentPage} из {totalPages} (всего {total} товаров)
      </span>
            {onLimitChange && (
        <label className="pagination-limit">
          Показывать:
          <select
            className="filter-select select-small"
            value={limit}
            onChange={(e) => onLimitChange(Number(e.target.value))}
          >
            {[10, 30, 50, 100].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
};

export default Pagination;