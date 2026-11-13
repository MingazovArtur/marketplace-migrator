import { useCallback, useEffect, useMemo } from 'react';
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { api } from '../api';

/* Список App-уровня: первые 50 товаров с дефолтной сортировкой — нужен для
 * фолбэка модалок (getProductById) и дашборда. Страница «Товары» ходит в тот
 * же эндпоинт со своими фильтрами — это отдельная запись кэша под тем же
 * префиксом ['products'], поэтому инвалидация префикса обновляет обе. */
const APP_LIST_FILTERS = {
  search: '',
  status: '',
  source: '',
  sort_by: 'created_at',
  sort_order: 'desc',
  skip: 0,
  limit: 50,
};

const DEFAULT_STATS = { total: 0, pending: 0, success: 0, error: 0, processing: 0 };

/* 401 от сервера = кука протухла: ретраить бессмысленно */
const isAuthError = (err) => {
  const msg = String(err?.message || '');
  return msg.includes('401') || msg.includes('Недействительный');
};

const retryPolicy = (failureCount, error) => !isAuthError(error) && failureCount < 2;

/**
 * Данные App-уровня (Round 7: переведён с ручного useState+useEffect на
 * TanStack Query — кэш, дедуп и инвалидация вместо проброса refreshKey).
 *
 * Контракт прежний: products (первые 50), stats, loading, loadData (принудительный
 * refetch), getProductById (фолбэк для модалек). 401 по-прежнему зовёт onAuthError.
 */
export const useProducts = (authed, onAuthError) => {
  const queryClient = useQueryClient();

  const statsQuery = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
    enabled: authed,
    retry: retryPolicy,
  });

  const productsQuery = useQuery({
    queryKey: ['products', 'app-list'],
    queryFn: () => api.getProducts(APP_LIST_FILTERS),
    enabled: authed,
    retry: retryPolicy,
    placeholderData: keepPreviousData,
  });

  // Разлогин по 401 (как в старом loadData) + очистка кэша при выходе:
  // кэш живёт в едином QueryClient и переживёт смену пользователя, а старые
  // товары не должны показываться следующему залогиненному.
  useEffect(() => {
    if (isAuthError(statsQuery.error) || isAuthError(productsQuery.error)) {
      onAuthError?.();
    }
  }, [statsQuery.error, productsQuery.error, onAuthError]);

  useEffect(() => {
    if (!authed) {
      queryClient.clear();
    }
  }, [authed, queryClient]);

  // Стабильная идентичность: [] пересоздавался бы каждый рендер и «дёргал» бы
  // useCallback/useMemo вниз по дереву (react-hooks/exhaustive-deps)
  const products = useMemo(() => productsQuery.data?.products ?? [], [productsQuery.data]);
  const stats = statsQuery.data ?? DEFAULT_STATS;
  const loading = authed && (statsQuery.isPending || productsQuery.isPending);

  // Принудительный refetch — прежняя семантика loadData из useMigration/refreshAll
  const loadData = useCallback(async () => {
    await Promise.all([statsQuery.refetch(), productsQuery.refetch()]);
  }, [statsQuery, productsQuery]);

  const getProductById = useCallback((id) => products.find((p) => p.id === id), [products]);

  return {
    products,
    stats,
    loading,
    loadData,
    getProductById,
  };
};
