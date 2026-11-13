import { GAP_LABELS, BLOCKING_GAP_FIELDS } from '../../constants/gaps';

/* Чистые функции подсчёта пропусков (Р4: вынесено из ProductsPage.jsx).
 * Используются баннером пропусков и панелью массовых действий. */

// Есть ли БЛОКИРУЮЩИЕ пропуски (цена 0 / нет фото) — от этого зависит цвет баннера:
// красный только когда миграция реально сломается, иначе — спокойное предупреждение
export const hasBlockingGaps = (gapEntries) =>
  gapEntries.some(([k]) => BLOCKING_GAP_FIELDS.includes(k));

// Чипы пропусков: три габарита (Ш×В×Д) с одинаковым счётчиком схлопываем
// в один «Габариты, мм — N», чтобы не читать три одинаковые строки
export const computeGapChips = (gapEntries, gaps) => {
  const g = gaps?.gaps || {};
  const dims = ['package_width_mm', 'package_height_mm', 'package_length_mm'];
  const counts = dims.map((f) => g[f] || 0);
  const same = counts[0] > 0 && counts.every((n) => n === counts[0]);
  const out = [];
  gapEntries.forEach(([k, n]) => {
    if (dims.includes(k) && same) {
      if (!out.some(([label]) => label === 'Габариты, мм')) out.push(['Габариты, мм', n]);
    } else {
      out.push([GAP_LABELS[k] || k, n]);
    }
  });
  return out;
};

// ✅ Пропуски в ВЫДЕЛЕННЫХ товарах (для badge и confirm)
export const computeSelectedGaps = (products, selected) => {
  if (!selected || selected.length === 0) return null;
  const selectedProducts = products.filter((p) => selected.includes(p.id));
  const gapsLocal = {};
  selectedProducts.forEach((p) => {
    const price = Number(p.price);
    if (!price || price <= 0 || isNaN(price)) gapsLocal.price = (gapsLocal.price || 0) + 1;
    if (!p.photos || p.photos.length === 0) gapsLocal.main_photo = (gapsLocal.main_photo || 0) + 1;
    [
      'vat_rate',
      'okpd_code',
      'package_weight_grams',
      'package_width_mm',
      'package_height_mm',
      'package_length_mm',
    ].forEach((f) => {
      if (p[f] === null || p[f] === undefined || p[f] === '' || p[f] === 0) {
        gapsLocal[f] = (gapsLocal[f] || 0) + 1;
      }
    });
  });
  return gapsLocal;
};

export const selectedBlockingTotal = (selectedGaps) =>
  selectedGaps ? BLOCKING_GAP_FIELDS.reduce((acc, k) => acc + (selectedGaps[k] || 0), 0) : 0;

export const selectedFillableTotal = (selectedGaps) =>
  selectedGaps
    ? Object.entries(selectedGaps)
        .filter(([k]) => !BLOCKING_GAP_FIELDS.includes(k))
        .reduce((acc, [, n]) => acc + n, 0)
    : 0;
