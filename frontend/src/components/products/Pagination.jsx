import React from 'react';
import Button from '../common/Button';
import { PAGE_SIZE_OPTIONS } from './tableUtils';

/* Пагинация таблицы товаров (Р4: вынесено из ProductsPage.jsx без изменения разметки). */
const Pagination = ({ total, skip, limit, page, pages, onSkipChange, onLimitChange }) => {
  if (!(total > 0)) return null;

  return (
    <div
      style={{
        display: 'flex',
        gap: '0.5rem',
        justifyContent: 'center',
        alignItems: 'center',
        marginTop: '0.75rem',
        flexWrap: 'wrap',
      }}
    >
      <Button
        variant="secondary"
        size="small"
        disabled={skip === 0}
        onClick={() => onSkipChange(0)}
        title="Первая страница"
      >
        « В начало
      </Button>
      <Button
        variant="secondary"
        size="small"
        disabled={skip === 0}
        onClick={() => onSkipChange(Math.max(0, skip - limit))}
      >
        ← Назад
      </Button>
      <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', padding: '0 0.25rem' }}>
        Стр. {page} из {pages} · всего {total}
      </span>
      <Button
        variant="secondary"
        size="small"
        disabled={skip + limit >= total}
        onClick={() => onSkipChange(skip + limit)}
      >
        Вперёд →
      </Button>
      <Button
        variant="secondary"
        size="small"
        disabled={skip + limit >= total}
        onClick={() => onSkipChange((pages - 1) * limit)}
        title="Последняя страница"
      >
        В конец »
      </Button>
      <select
        className="form-input"
        style={{
          width: 64,
          padding: '0.25rem 0.4rem',
          marginLeft: '0.5rem',
          textAlign: 'center',
          fontSize: '0.85rem',
        }}
        value={limit}
        onChange={(e) => onLimitChange(Number(e.target.value))}
        title="Товаров на странице"
      >
        {PAGE_SIZE_OPTIONS.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
    </div>
  );
};

export default Pagination;
