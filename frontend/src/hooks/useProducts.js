import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api';

export const useProducts = (token, onAuthError) => {
  const [products, setProducts] = useState([]);
  const [stats, setStats] = useState({ total: 0, pending: 0, success: 0, error: 0, processing: 0 });
  const [loading, setLoading] = useState(false);
  const [totalProducts, setTotalProducts] = useState(0);

  // Состояния фильтров и пагинации
  const [filters, setFilters] = useState({
    search: '',
    status: '',
    source: '',
    sort_by: 'created_at',
    sort_order: 'desc',
    skip: 0,
    limit: 50,
  });

  const onAuthErrorRef = useRef(onAuthError);

  useEffect(() => {
    onAuthErrorRef.current = onAuthError;
  }, [onAuthError]);

  const loadData = useCallback(async () => {
    if (!token) {
      setProducts([]);
      setStats({ total: 0, pending: 0, success: 0, error: 0, processing: 0 });
      setTotalProducts(0);
      return;
    }

    setLoading(true);
    try {
      const [statsData, productsData] = await Promise.all([
        api.getStats(),
        api.getProducts(filters),
      ]);
      setStats(statsData);
      setProducts(productsData.products || []);
      setTotalProducts(productsData.total || 0);
    } catch (err) {
      if (err.message.includes('401') || err.message.includes('Недействительный')) {
        onAuthErrorRef.current?.();
      }
    } finally {
      setLoading(false);
    }
  }, [token, filters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const availableForBatch = products.filter(
    (p) => p.status !== 'success' && p.status !== 'processing'
  ).length;

  const getProductById = useCallback(
    (id) => {
      return products.find((p) => p.id === id);
    },
    [products]
  );

  const updateFilters = useCallback((newFilters) => {
    setFilters((prev) => ({ ...prev, ...newFilters }));
  }, []);

  const setPage = useCallback((page) => {
    setFilters((prev) => ({ ...prev, skip: (page - 1) * prev.limit }));
  }, []);

  return {
    products,
    stats,
    loading,
    loadData,
    setProducts,
    availableForBatch,
    getProductById,
    totalProducts,
    filters,
    updateFilters,
    setPage,
  };
};
