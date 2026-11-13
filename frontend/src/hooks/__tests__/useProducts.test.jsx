import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useProducts } from '../useProducts';

/* Мокаем агрегатор api: useProducts интересуют только getStats/getProducts */
vi.mock('../../api', () => ({
  api: {
    getStats: vi.fn(),
    getProducts: vi.fn(),
  },
}));

import { api } from '../../api';

const STATS = { total: 3, pending: 1, success: 1, error: 1, processing: 0 };
const LIST = { products: [{ id: 1 }, { id: 2 }, { id: 3 }], total: 3 };

const createWrapper = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
};

describe('useProducts (TanStack Query)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getStats.mockResolvedValue(STATS);
    api.getProducts.mockResolvedValue(LIST);
  });

  it('без авторизации не ходит в сеть и отдаёт пустые данные', async () => {
    const { result } = renderHook(() => useProducts(false, undefined), {
      wrapper: createWrapper(),
    });

    expect(api.getProducts).not.toHaveBeenCalled();
    expect(api.getStats).not.toHaveBeenCalled();
    expect(result.current.products).toEqual([]);
    expect(result.current.stats).toEqual({
      total: 0,
      pending: 0,
      success: 0,
      error: 0,
      processing: 0,
    });
  });

  it('загружает список и статистику, отдаёт их наружу', async () => {
    const { result } = renderHook(() => useProducts(true, undefined), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.products).toHaveLength(3));
    expect(result.current.stats).toEqual(STATS);
    expect(api.getStats).toHaveBeenCalledTimes(1);
    expect(api.getProducts).toHaveBeenCalledTimes(1);

    // getProductById находит товар из загруженного списка
    expect(result.current.getProductById(2)).toEqual({ id: 2 });
    expect(result.current.getProductById(99)).toBeUndefined();
  });

  it('401 от сервера вызывает onAuthError (разлогин)', async () => {
    api.getStats.mockRejectedValue(new Error('Не авторизован (HTTP 401)'));
    api.getProducts.mockResolvedValue(LIST);
    const onAuthError = vi.fn();

    renderHook(() => useProducts(true, onAuthError), { wrapper: createWrapper() });

    await waitFor(() => expect(onAuthError).toHaveBeenCalled());
  });

  it('статистика доступна, даже если список ещё грузится', async () => {
    let resolveList;
    api.getProducts.mockImplementation(() => new Promise((r) => (resolveList = () => r(LIST))));

    const { result } = renderHook(() => useProducts(true, undefined), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.stats).toEqual(STATS));
    expect(result.current.products).toEqual([]);
    expect(result.current.loading).toBe(true);

    resolveList();
    await waitFor(() => expect(result.current.products).toHaveLength(3));
  });
});
