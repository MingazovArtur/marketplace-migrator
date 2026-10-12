import React from 'react';
import Button from './Button';

/**
 * Универсальное пустое состояние.
 * icon принимает JSX (<Icon ... />) или строку.
 */
const EmptyState = ({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  secondaryLabel,
  onSecondary,
}) => (
  <div className="empty-state">
    <div
      className="empty-state-icon"
      style={{ display: 'flex', justifyContent: 'center', color: 'var(--accent-primary)' }}
    >
      {icon}
    </div>
    <h2>{title}</h2>
    <p>{description}</p>
    <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', flexWrap: 'wrap' }}>
      {onAction && <Button onClick={onAction}>{actionLabel}</Button>}
      {onSecondary && (
        <Button variant="secondary" onClick={onSecondary}>
          {secondaryLabel}
        </Button>
      )}
    </div>
  </div>
);

export default EmptyState;
