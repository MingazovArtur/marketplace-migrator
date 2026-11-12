import React from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { GAP_LABELS } from '../../constants/gaps';
import {
  computeGapChips,
  computeSelectedGaps,
  hasBlockingGaps,
  selectedBlockingTotal,
  selectedFillableTotal,
} from './gapsHelpers';

/* Баннер пропусков над таблицей товаров (Р4: вынесено из ProductsPage.jsx).
 * Красный — если есть блокирующие пропуски (цена 0 / нет фото), иначе предупреждение. */
const GapsBanner = ({ gaps, gapEntries, products, selected, applyLoading, onApplyDefaults }) => {
  if (!gaps || !(gaps.total > 0) || !(gapEntries.length > 0)) return null;

  const blocking = hasBlockingGaps(gapEntries);
  const chips = computeGapChips(gapEntries, gaps);
  const sel = selected.length > 0 ? computeSelectedGaps(products, selected) : null;
  const selBlocking = selectedBlockingTotal(sel);
  const selFillable = selectedFillableTotal(sel);

  return (
    <div
      className={`alert gaps-banner ${blocking ? 'alert-error' : 'alert-warning'}`}
      style={{ marginBottom: '0.75rem' }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
          <strong>
            {blocking ? '❌ Не всё готово к выгрузке' : '⚠️ Не хватает полей'} —{' '}
            {gaps.products_with_gaps ?? gaps.total} из {gaps.total} товаров:
          </strong>
          {chips.map(([label, n]) => (
            <span key={label} className="gap-chip">
              {label} <strong>{n}</strong>
            </span>
          ))}
        </div>
        {selected.length > 0 && selBlocking + selFillable > 0 && (
          <div style={{ marginTop: '0.3rem', fontSize: '0.8rem', opacity: 0.9 }}>
            В выделенных ({selected.length}):{' '}
            {Object.entries(sel || {})
              .filter(([, n]) => n > 0)
              .map(([k, n]) => `${GAP_LABELS[k] || k} — ${n}`)
              .join('; ')}
          </div>
        )}
        <div style={{ marginTop: '0.3rem', fontSize: '0.8rem', opacity: 0.75 }}>
          {blocking
            ? 'Цена 0 и отсутствие фото блокируют миграцию — заполните их. Остальные поля дозаполнятся из «Дефолтов».'
            : 'Кнопка «Заполнить из дефолтов» допишет пустые НДС, ТН ВЭД, вес, габариты и цену по умолчанию.'}
        </div>
      </div>
      <Button
        size="small"
        onClick={() => onApplyDefaults('all')}
        loading={applyLoading}
        title="Дозаполнит пустые поля у всех товаров из глобальных дефолтов и дефолтов категорий"
        style={{ alignSelf: 'center', whiteSpace: 'nowrap' }}
      >
        <Icon name="edit" size={15} /> Заполнить из дефолтов
      </Button>
    </div>
  );
};

export default GapsBanner;
