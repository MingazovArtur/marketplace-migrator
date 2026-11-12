/* Константы и форматтеры таблицы товаров (Р4: вынесено из ProductsPage.jsx). */

export const STATUS_META = {
  pending: { label: 'Ожидает', cls: 'badge-pending' },
  processing: { label: 'В работе', cls: 'badge-processing' },
  success: { label: 'Успешно', cls: 'badge-success' },
  error: { label: 'Ошибка', cls: 'badge-error' },
};

export const SORT_OPTIONS = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
  { value: 'name_asc', label: 'Название А→Я' },
  { value: 'name_desc', label: 'Название Я→А' },
  { value: 'price_asc', label: 'Цена ↑' },
  { value: 'price_desc', label: 'Цена ↓' },
];

// Ширины по умолчанию — ТОЛЬКО для компактных колонок. Колонка «Товар» (name)
// без ширины: в table-layout:fixed она забирает всё свободное место, а остальные
// колонки держатся по содержимому (раньше лишние пиксели распихивались
// поровну и «Цена»/«Статус» раздувались втрое шире своего содержимого).
export const DEFAULT_WIDTHS = {
  check: 36,
  id: 56,
  category: 190,
  price: 96,
  status: 100,
  actions: 156,
};

export const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];

// Цена в человеческом формате: 99.97 → «99,97», 1000 → «1 000»
export const fmtPrice = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
};
