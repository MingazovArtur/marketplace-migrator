import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import { api } from '../../api';
import Icon from '../icons';

const VariantsModal = ({ isOpen, onClose, product, onSave }) => {
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && product) {
      setVariants(product.variants || []);
    }
  }, [isOpen, product]);

  const handleAdd = () => {
    setVariants([
      ...variants,
      { sku: '', size: '', color: '', price: null, stock: null, sort_order: variants.length },
    ]);
  };

  const handleRemove = (index) => {
    setVariants(variants.filter((_, i) => i !== index));
  };

  const handleChange = (index, field, value) => {
    const updated = [...variants];
    updated[index] = { ...updated[index], [field]: value };
    setVariants(updated);
  };

  const handleSave = async () => {
    if (!product) return;
    setLoading(true);
    try {
      const valid = variants
        .filter((v) => v.sku && String(v.sku).trim())
        .map((v) => ({
          sku: String(v.sku).trim(),
          size: v.size ? String(v.size).trim() : null,
          color: v.color ? String(v.color).trim() : null,
          price: v.price === '' || v.price == null ? null : Number(v.price),
          stock: v.stock === '' || v.stock == null ? null : Number(v.stock),
          sort_order: v.sort_order ?? 0,
        }));
      await api.setVariants(product.id, valid);
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
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="variants" size={22} />
            Вариации: {product.name}
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Каждая вариация — отдельный SKU (размер/цвет) со своей ценой и остатком.
        </p>

        <div className="variants-table-wrap">
          <table className="variants-table">
            <thead>
              <tr>
                <th>SKU (ШК)</th>
                <th style={{ width: 100 }}>Размер</th>
                <th style={{ width: 120 }}>Цвет</th>
                <th style={{ width: 110 }}>Цена, ₽</th>
                <th style={{ width: 100 }}>Остаток</th>
                <th style={{ width: 50 }}></th>
              </tr>
            </thead>
            <tbody>
              {variants.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '1rem' }}>
                    Вариаций нет. Добавьте первую или импортируйте из файла.
                  </td>
                </tr>
              )}
              {variants.map((v, idx) => (
                <tr key={idx}>
                  <td>
                    <input
                      className="form-input"
                      value={v.sku || ''}
                      placeholder="1000041010180"
                      onChange={(e) => handleChange(idx, 'sku', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="form-input"
                      value={v.size || ''}
                      placeholder="92"
                      onChange={(e) => handleChange(idx, 'size', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="form-input"
                      value={v.color || ''}
                      placeholder="Розовый"
                      onChange={(e) => handleChange(idx, 'color', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="form-input"
                      type="number"
                      value={v.price ?? ''}
                      placeholder="990"
                      onChange={(e) => handleChange(idx, 'price', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="form-input"
                      type="number"
                      value={v.stock ?? ''}
                      placeholder="10"
                      onChange={(e) => handleChange(idx, 'stock', e.target.value)}
                    />
                  </td>
                  <td>
                    <button className="btn-icon-danger" onClick={() => handleRemove(idx)} title="Удалить">
                      🗑
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Button variant="secondary" onClick={handleAdd} style={{ marginTop: '0.75rem' }}>
          + Добавить вариацию
        </Button>

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button onClick={handleSave} disabled={loading} loading={loading}>
            Сохранить ({variants.length})
          </Button>
        </div>
      </div>
    </div>
  );
};

export default VariantsModal;