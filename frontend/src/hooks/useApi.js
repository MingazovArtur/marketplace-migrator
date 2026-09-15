/**
 * Hook для работы с API с единой обработкой ошибок и loading states
 */
import { useState, useCallback } from 'react';
import { api } from '../api';

export const useApi = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const callApi = useCallback(async (apiCall, errorMessage = 'Произошла ошибка') => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await apiCall();
      return result;
    } catch (err) {
      const errorMsg = err.message || errorMessage;
      setError(errorMsg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    loading,
    error,
    setError,
    clearError,
    callApi,
    api
  };
};