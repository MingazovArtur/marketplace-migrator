import React, { useState, useEffect, useRef } from 'react';
import Button from '../common/Button';
import { api } from '../../api';
import Icon from '../icons';

const AttributesModal = ({ isOpen, onClose, product, onSave, onNotify }) => {
  const [attributes, setAttributes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  // R29: стабильные ключи строк — key={index} при удалении средней строки
  // «склеивал» стейты соседних инпутов (React переиспользовал DOM по позиции)
  const keySeq = useRef(0);

  useEffect(() => {
    if (isOpen && product) {
      keySeq.current = 0;
      setAttributes(
        (product.attributes || []).map((attr) => ({ ...attr, _key: ++keySeq.current }))
      );
      setError(''); // Сбрасываем ошибку при каждом открытии
    }
  }, [isOpen, product]);

  const handleAdd = () => {
    setAttributes([
      ...attributes,
      { name: '', value: '', sort_order: attributes.length, _key: ++keySeq.current },
    ]);
  };

  const handleRemove = (index) => {
    setAttributes(attributes.filter((_, i) => i !== index));
  };

  const handleChange = (index, field, value) => {
    const updated = [...attributes];
    updated[index][field] = value;
    setAttributes(updated);
  };

  const handleSave = async () => {
    setLoading(true);
    setError('');
    try {
      // R29: служебный _key — только для React-ключей, в API не отправляем
      const payload = attributes.map(({ _key, ...rest }) => rest);
      const result = await api.setAttributes(product.id, payload);
      onSave();

      // ✅ Показываем уведомления о нормализации
      if (result?.normalizations?.length > 0) {
        const normalizedList = result.normalizations
          .map((n) => `«${n.field}»: "${n.original}" → "${n.normalized}"`)
          .join('\n');
        onNotify?.(
          `✨ ${result.normalizations.length} значений нормализовано под словарь площадки:\n${normalizedList}`
        );
      }

      if (result?.warnings?.length > 0) {
        const warningList = result.warnings.map((w) => `${w.field}: ${w.value}`).join(', ');
        onNotify?.(
          `⚠️ ${result.warnings.length} значений не найдены в словаре площадки: ${warningList}`
        );
      }

      onClose();
    } catch (e) {
      setError(e.message || 'Ошибка сохранения характеристик');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen || !product) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">🏷 Характеристики: {product.name}</h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        {error && (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            <div>{error}</div>
          </div>
        )}

        <div className="attributes-list">
          {attributes.map((attr, idx) => (
            <div key={attr._key ?? `row-${idx}`} className="attribute-row">
              <input
                className="form-input"
                placeholder="Название (Размер, Цвет...)"
                value={attr.name}
                onChange={(e) => handleChange(idx, 'name', e.target.value)}
                style={{ flex: 1 }}
              />
              <input
                className="form-input"
                placeholder="Значение"
                value={attr.value}
                onChange={(e) => handleChange(idx, 'value', e.target.value)}
                style={{ flex: 2 }}
              />
              <button type="button" className="btn btn-danger" onClick={() => handleRemove(idx)}>
                🗑
              </button>
            </div>
          ))}
        </div>

        <Button
          type="button"
          variant="secondary"
          onClick={handleAdd}
          style={{ marginTop: '0.5rem' }}
        >
          + Добавить характеристику
        </Button>

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Отмена
          </Button>
          <Button onClick={handleSave} disabled={loading} loading={loading}>
            Сохранить
          </Button>
        </div>
      </div>
    </div>
  );
};

export default AttributesModal;
