import { useEffect, useState } from 'react';
import { api } from '../api';

/**
 * Проверяет, сопоставлена ли категория товара для пары sourcePlatform → targetPlatform.
 *
 * Логика:
 *   1. Пытаемся найти категорию в справочнике источника по имени.
 *   2. Если нашли — проверяем маппинг по source_category_id.
 *   3. Если справочника нет (404, например для файловых импортов) —
 *      пробуем найти маппинг напрямую по source_category_name.
 *
 * Не спамит 404-ошибками в консоль: api.getCategories мягко возвращает []
 * при отсутствии маршрута на бэкенде.
 */
export function useCategoryMappingCheck(sourcePlatform, targetPlatform, categoryName) {
  const [state, setState] = useState({ checked: false, isMapped: false, loading: false });

  useEffect(() => {
    let cancelled = false;

    if (!sourcePlatform || !targetPlatform || !categoryName) {
      setState({ checked: false, isMapped: false, loading: false });
      return undefined;
    }

    setState((s) => ({ ...s, loading: true }));

    Promise.all([
      // ✅ api.getCategories: кодирует URL, при 404 возвращает [] (без throw)
      api.getCategories(sourcePlatform).catch(() => ({ categories: [] })),
      // ✅ api.getCategoryMapping: использует URLSearchParams (безопасно для кириллицы)
      api.getCategoryMapping(sourcePlatform, targetPlatform).catch(() => ({ mappings: [] })),
    ])
      .then(([cats, maps]) => {
        if (cancelled) return;

        const name = String(categoryName).trim().toLowerCase();
        const categories = cats.categories || [];
        const mappings = maps.mappings || [];

        // Ищем категорию в справочнике источника
        const cat = categories.find((c) => String(c.name).trim().toLowerCase() === name);

        let isMapped = false;

        if (cat) {
          // Вариант 1: справочник есть, проверяем по ID
          isMapped = mappings.some((m) => String(m.source_category_id) === String(cat.id));
        } else {
          // Вариант 2: справочника нет (файловый импорт / 404) — ищем по имени
          isMapped = mappings.some(
            (m) =>
              String(m.source_category_name || '')
                .trim()
                .toLowerCase() === name
          );
        }

        setState({ checked: true, isMapped, loading: false });
      })
      .catch(() => {
        if (!cancelled) setState({ checked: true, isMapped: false, loading: false });
      });

    return () => {
      cancelled = true;
    };
  }, [sourcePlatform, targetPlatform, categoryName]);

  return state;
}
