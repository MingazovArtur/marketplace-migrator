/**
 * Hook для управления товарами и статистикой
 */
import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

export const useProducts = (onAuthError) => {
  const [products, setProducts] = useState([]);
  const [stats, setStats] = useState({ total: 0, pending: 0, success: 0, error: 0, processing: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const [statsData, productsData] = await Promise.all([
        api.getStats(),
        api.getProducts()
      ]);
      
      setStats(statsData);
      setProducts(productsData.products || []);
    } catch (err) {
      if (err.message.includes('401') || err.message.includes('Недействительный')) {
        onAuthError?.();
      } else {
        setError('Не удалось загрузить данные');
      }
    } finally {
      setLoading(false);
    }
  }, [onAuthError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Вычисляемые значения
  const availableForBatch = products.filter(
    p => p.status !== 'success' && p.status !== 'processing'
  ).length;

  const getProductById = useCallback((id) => {
    return products.find(p => p.id === id);
  }, [products]);

  return {
    products,
    stats,
    loading,
    error,
    setError,
    loadData,
    setProducts,
    availableForBatch,
    getProductById
  };
};