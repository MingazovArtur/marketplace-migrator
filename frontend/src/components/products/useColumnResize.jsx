import React, { useCallback, useState } from 'react';
import { DEFAULT_WIDTHS } from './tableUtils';

/* Хук ресайза колонок таблицы товаров (Р4: вынесено из ProductsPage.jsx).
 * Возвращает colWidths (для кнопки «Сбросить ширину» в тулбаре страницы)
 * и компонент Resizer, который вставляется в ячейки thead. */
export const useColumnResize = () => {
  const [colWidths, setColWidths] = useState({});

  const resetCol = (key) => {
    setColWidths((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const startResize = useCallback(
    (key, e) => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.pageX;
      const th = e.target.closest('th');
      const startW = colWidths[key] || th?.offsetWidth || DEFAULT_WIDTHS[key] || 120;

      const onMove = (ev) => {
        const w = Math.max(60, startW + (ev.pageX - startX));
        setColWidths((prev) => ({ ...prev, [key]: w }));
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [colWidths]
  );

  const colStyle = (key) => ({ width: colWidths[key] || DEFAULT_WIDTHS[key] });

  const Resizer = ({ colKey }) => (
    <span
      className="col-resizer"
      onMouseDown={(e) => startResize(colKey, e)}
      onDoubleClick={(e) => {
        e.stopPropagation();
        resetCol(colKey);
      }}
      onClick={(e) => e.stopPropagation()}
      title="Тянуть — ширина, двойной клик — сброс"
    />
  );

  return { colWidths, setColWidths, resetCol, startResize, colStyle, Resizer };
};
