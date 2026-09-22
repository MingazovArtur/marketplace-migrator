import { useEffect, useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? '/api' : 'http://localhost:8000/api');

const authHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

/**
 * Проверяет, сопоставлена ли категория товара (по имени) для пары
 * sourcePlatform → targetPlatform.
 *
 * Логика: имя категории → id в справочнике источника → есть ли маппинг с этим id.
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
      fetch(`${API_URL}/categories/${sourcePlatform}`)
        .then((r) => (r.ok ? r.json() : { categories: [] })),
      fetch(
        `${API_URL}/category-mapping?source_platform=${sourcePlatform}&target_platform=${targetPlatform}`,
        { headers: authHeaders() }
      ).then((r) => (r.ok ? r.json() : { mappings: [] })),
    ])
      .then(([cats, maps]) => {
        if (cancelled) return;
        const name = String(categoryName).trim().toLowerCase();
        const cat = (cats.categories || []).find(
          (c) => String(c.name).trim().toLowerCase() === name
        );
        const isMapped =
          !!cat &&
          (maps.mappings || []).some((m) => String(m.source_category_id) === String(cat.id));
        setState({ checked: true, isMapped, loading: false });
      })
      .catch(() => {
        if (!cancelled) setState({ checked: true, isMapped: false, loading: false });
      });

    return () => { cancelled = true; };
  }, [sourcePlatform, targetPlatform, categoryName]);

  return state;
}