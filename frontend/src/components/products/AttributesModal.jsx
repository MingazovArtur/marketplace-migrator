import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import { api } from '../../api';

const AttributesModal = ({ isOpen, onClose, product, onSave }) => {
  const [attributes, setAttributes] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && product) {
      setAttributes(product.attributes || []);
    }
  }, [isOpen, product]);

  const handleAdd = () => {
    setAttributes([...attributes, { name: '', value: '', sort_order: attributes.length }]);
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
    if (!product) return;
    setLoading(true);
    try {
      const validAttrs = attributes.filter(a => a.name.trim() && a.value.trim());
      await api.setAttributes(product.id, validAttrs);
      onSave();
      onClose();
    } catch (err) {
      alert('Ошибка сохранения: ' + err.message);
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
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="attributes-list">
          {attributes.map((attr, idx) => (
            <div key={idx} className="attribute-row">
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
              <button className="btn btn-danger" onClick={() => handleRemove(idx)}>
                🗑
              </button>
            </div>
          ))}
        </div>

        <Button variant="secondary" onClick={handleAdd} style={{ marginTop: '0.5rem' }}>
          + Добавить характеристику
        </Button>

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button onClick={handleSave} disabled={loading} loading={loading}>
            Сохранить
          </Button>
        </div>
      </div>
    </div>
  );
};

export default AttributesModal;