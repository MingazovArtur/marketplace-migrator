import React from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { getStaleness } from './specsUtils';

/* Карточка категории в списке спеков (Р3: вынесено из SpecsPage.jsx).
 * Лёгкая карточка без атрибутов: точка свежести, имя, ID, «Атрибуты», удаление (админ). */
const CategoryCard = ({ cat, isAdmin, isDeleting, onOpenDetail, onDelete }) => {
  const st = getStaleness(cat.fetched_at);
  const itemKey = cat.category_id || cat.category_name;

  return (
    <div className="card spec-card" style={{ padding: '0.75rem 1.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: st.color,
                display: 'inline-block',
              }}
              title={st.label}
            />
            <strong style={{ fontSize: '1rem' }}>{cat.category_name}</strong>
          </div>
          {cat.category_id && cat.category_id !== cat.category_name && (
            <div
              style={{
                color: 'var(--text-muted)',
                fontSize: '0.8rem',
                marginTop: '0.15rem',
              }}
            >
              ID: {cat.category_id}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <Button variant="secondary" size="small" onClick={() => onOpenDetail(itemKey)}>
            <Icon name="tag" size={15} /> Атрибуты
          </Button>
          {isAdmin && (
            <Button
              variant="outline"
              size="small"
              onClick={() => onDelete(cat)}
              disabled={isDeleting}
              loading={isDeleting}
              title={`Удалить спецификацию «${cat.category_name}»`}
              style={{ color: 'var(--accent-danger)' }}
            >
              <Icon name="trash" size={15} />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default CategoryCard;
