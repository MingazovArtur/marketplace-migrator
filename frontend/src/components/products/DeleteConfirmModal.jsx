import React, { useState } from 'react';
import Button from '../common/Button';
import Icon from '../icons';

/**
 * Модалка подтверждения удаления.
 * mode: 'single' | 'bulk' | 'all'
 * Для mode='all' требует ввод слова УДАЛИТЬ (защита от случайного клика).
 * isAdmin меняет формулировки: «все товары в системе» vs «все мои товары».
 * Безопасность гарантирует backend: не-админ удаляет только свои товары.
 */
const DeleteConfirmModal = ({ mode = 'single', count = 1, isAdmin = false, loading, onConfirm, onClose }) => {
  const [text, setText] = useState('');

  const isAll = mode === 'all';
  const needText = isAll && text.trim().toUpperCase() !== 'УДАЛИТЬ';

  const title = isAll
    ? (isAdmin ? 'Удалить ВСЕ товары в системе?' : 'Удалить ВСЕ ваши товары?')
    : mode === 'bulk'
      ? `Удалить выбранные товары (${count})?`
      : 'Удалить товар?';

  const description = isAll
    ? (isAdmin
      ? '⚠️ Будут удалены ВСЕ товары ВСЕХ пользователей вместе с характеристиками и вариантами. Журналы операций сохранятся. Действие необратимо.'
      : 'Будут удалены все ВАШИ товары (все страницы, не только текущая) вместе с характеристиками и вариантами. Журналы операций сохранятся. Действие необратимо.')
    : mode === 'bulk'
      ? 'Выбранные товары будут удалены вместе с характеристиками и вариантами. Действие необратимо.'
      : 'Товар будет удалён вместе с характеристиками и вариантами. Действие необратимо.';

  return (
    <div className="modal-overlay" onClick={loading ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title" style={{ color: 'var(--accent-danger)' }}>
            <Icon name="trash" size={22} /> {title}
          </h2>
          <button type="button" className="close-btn" onClick={onClose} disabled={loading} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
          <div>{description}</div>
        </div>

        {isAll && (
          <>
            <label className="form-label">
              Введите слово <strong>УДАЛИТЬ</strong> для подтверждения
            </label>
            <input
              className="form-input"
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="УДАЛИТЬ"
              disabled={loading}
              autoFocus
            />
            <p className="form-hint">
              {isAdmin
                ? 'Это действие затронет всех пользователей системы.'
                : 'Это действие затронет только ваши товары — товары других пользователей не пострадают.'}
            </p>
          </>
        )}

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={loading}>Отмена</Button>
          <Button
            onClick={onConfirm}
            disabled={loading || needText}
            loading={loading}
            style={{ background: 'var(--accent-danger)', borderColor: 'var(--accent-danger)' }}
          >
            <Icon name="trash" size={16} /> Удалить
          </Button>
        </div>
      </div>
    </div>
  );
};

export default DeleteConfirmModal;