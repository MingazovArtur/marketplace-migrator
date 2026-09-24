import React, { useState, useEffect, useMemo } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { PLATFORMS } from '../../utils/platformUtils';
import { useCategoryMappingCheck } from '../../hooks/useCategoryMapping';
import { api } from '../../api';

const MigrateModal = ({ isOpen, onClose, product, onConfirm, loading }) => {
  const [platform, setPlatform] = useState('ozon');
  const [autoExport, setAutoExport] = useState(true);
  const [edited, setEdited] = useState(null);
  const [specNames, setSpecNames] = useState([]);
  const [specsLoading, setSpecsLoading] = useState(false);

  /* ✅ Хук ДО early return — иначе нарушение правил хуков */
  const { checked, isMapped } = useCategoryMappingCheck(
    product?.source,
    platform,
    product?.category
  );

  // useEffect инициализации формы
  useEffect(() => {
    if (isOpen && product) {
      setEdited({
        name: product.name || '',
        price: product.price ?? '',
        category: product.mapped_category || product.category || '',
      });
      setAutoExport(true);
    }
  }, [isOpen, product]);

  // useEffect загрузки спеков
  useEffect(() => {
    let cancelled = false;
    if (!isOpen) return undefined;
    setSpecsLoading(true);
    api
      .getSpecNames(platform)
      .then((names) => { if (!cancelled) setSpecNames(Array.isArray(names) ? names : []); })
      .catch(() => { if (!cancelled) setSpecNames([]); })
      .finally(() => { if (!cancelled) setSpecsLoading(false); });
    return () => { cancelled = true; };
  }, [isOpen, platform]);

  // ✅ useMemo ДО early return — иначе "Rendered more hooks than previous render"
  const categoryValue = (edited?.category || '').trim();
  const filteredSpecs = useMemo(() => {
    if (!specNames.length) return [];
    const q = categoryValue.toLowerCase();
    if (!q) return specNames.slice(0, 100);
    const starts = specNames.filter((n) => n.toLowerCase().startsWith(q));
    const contains = specNames.filter(
      (n) => !n.toLowerCase().startsWith(q) && n.toLowerCase().includes(q)
    );
    return [...starts, ...contains].slice(0, 200);
  }, [specNames, categoryValue]);

  // ✅ Валидация — тоже до early return (это просто вычисление, не хук,
  //    но держим рядом с useMemo для ясности)
  const categoryValid = !categoryValue || specNames.includes(categoryValue);
  const specsReady = specNames.length > 0;
  const categoryInvalid = specsReady && !categoryValid;

  // ✅ Единственный early return — ПОСЛЕ ВСЕХ хуков
  if (!isOpen || !product) return null;

  const sourceName = PLATFORMS.find((p) => p.id === product.source)?.name || product.source;
  const targetName = PLATFORMS.find((p) => p.id === platform)?.name || platform;

  const handleChange = (field, value) => setEdited((e) => ({ ...e, [field]: value }));
  const handleConfirm = () => onConfirm(product.id, platform, edited, autoExport);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="migrate" size={22} /> Миграция карточки
          </h2>
          <button type="button" className="close-btn" onClick={onClose} title="Закрыть">
            <Icon name="close" size={16} />
          </button>
        </div>

        <div className="migrate-product-card">
          <div className="product-name">{product.name}</div>
          <div className="product-sub">
            {product.sku && <>SKU: {product.sku} · </>}
            {product.brand || 'Без бренда'}
            {product.price ? ` · ${Number(product.price).toLocaleString('ru-RU')} ₽` : ''}
          </div>
        </div>

        <label className="form-label">Целевая площадка:</label>
        <div className="platform-selector">
          {PLATFORMS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`platform-btn ${platform === p.id ? 'platform-btn-active' : ''}`}
              onClick={() => setPlatform(p.id)}
            >
              {p.name}
            </button>
          ))}
        </div>

        {/* Предупреждение: категория источника не сопоставлена */}
        {checked && !isMapped && product.category && (
          <div
            className="modal-hint-box"
            style={{
              borderColor: 'rgba(245, 158, 11, 0.4)',
              background: 'rgba(245, 158, 11, 0.08)',
            }}
          >
            <span className="hint-icon">
              <Icon name="warning" size={18} />
            </span>
            <p>
              Категория «{product.category}» не сопоставлена для перехода{' '}
              <strong>{sourceName} → {targetName}</strong>. При миграции будет использовано
              значение из поля «Категория назначения» ниже. Настроить соответствие можно в разделе
              «Маппинг» (боковое меню).
            </p>
          </div>
        )}

        <label className="form-label">Данные карточки (можно править):</label>

        <label className="form-label">Название</label>
        <input
          className="form-input"
          value={edited?.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
        />

        <label className="form-label">Цена, ₽</label>
        <input
          className="form-input"
          type="number"
          value={edited?.price ?? ''}
          onChange={(e) => handleChange('price', e.target.value)}
        />

        {/* ================= Категория: выбор ИЗ спеков площадки ================= */}
        <label className="form-label">
          Категория назначения{specsReady ? ` (${targetName})` : ''}
        </label>
        <input
          className="form-input"
          list="migrate-spec-categories"
          value={edited?.category || ''}
          onChange={(e) => handleChange('category', e.target.value)}
          placeholder={specsLoading ? 'Загружаю список категорий…' : 'Начните вводить: Одежда / Футболка…'}
          style={categoryInvalid ? { borderColor: 'var(--accent-danger)' } : undefined}
        />
        <datalist id="migrate-spec-categories">
          {filteredSpecs.map((n) => (
            <option key={n} value={n} />
          ))}
        </datalist>
        <p className="form-hint">
          {specsLoading && 'Загрузка списка категорий…'}
          {!specsLoading && specsReady && (
            <>
              Выберите точное имя из списка спеков {targetName} (формат «Родитель / Тип»).
              Доступно вариантов: {specNames.length}.
              {categoryValue && categoryValid && ' ✅ Имя найдено в спеках.'}
            </>
          )}
          {!specsLoading && !specsReady && (
            <>Спеки {targetName} не загружены — оставьте поле пустым (сработает авто-подбор) или задайте категорию в «Маппинг».</>
          )}
        </p>

        {/* Блокирующее предупреждение: имя не из спеков */}
        {categoryInvalid && (
          <div
            className="modal-hint-box"
            style={{
              borderColor: 'rgba(239, 68, 68, 0.5)',
              background: 'rgba(239, 68, 68, 0.08)',
            }}
          >
            <span className="hint-icon">
              <Icon name="warning" size={18} />
            </span>
            <p>
              Категории «{categoryValue}» нет в спеках {targetName} — миграция завершится ошибкой,
              а выгрузка не сформируется. Выберите имя из выпадающего списка выше
              или очистите поле (тогда категория подберётся автоматически по названию товара).
            </p>
          </div>
        )}

        <label className="bulk-check" style={{ margin: '1rem 0 0' }}>
          <input
            type="checkbox"
            checked={autoExport}
            onChange={(e) => setAutoExport(e.target.checked)}
          />
          Сразу скачать файл для загрузки в кабинет {platform}
        </label>

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose}>Отмена</Button>
          <Button
            onClick={handleConfirm}
            disabled={loading || categoryInvalid}
            loading={loading}
            title={categoryInvalid ? 'Категория не из списка спеков' : undefined}
          >
            <Icon name="migrate" size={16} /> Мигрировать
          </Button>
        </div>
      </div>
    </div>
  );
};

export default MigrateModal;