/* Хелперы страницы «Спецификации площадок» (Р3: вынесено из SpecsPage.jsx). */

/* Оценка свежести спека */
export const getStaleness = (fetchedAt) => {
  if (!fetchedAt) return { level: 'none', label: 'Не загружено', color: 'var(--text-muted)' };
  const days = Math.floor((Date.now() - new Date(fetchedAt).getTime()) / 86400000);
  if (days <= 7)
    return { level: 'fresh', label: `Обновлено ${days} дн. назад`, color: 'var(--accent-success)' };
  if (days <= 30)
    return {
      level: 'normal',
      label: `Обновлено ${days} дн. назад`,
      color: 'var(--accent-warning)',
    };
  return { level: 'stale', label: `Устарело (${days} дн.)`, color: 'var(--accent-danger)' };
};

export const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';
