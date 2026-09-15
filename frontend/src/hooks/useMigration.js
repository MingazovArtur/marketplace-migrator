/**
 * Hook для управления миграцией товаров с polling и блокировкой
 */
import { useState, useCallback, useRef } from 'react';
import { api } from '../api';

export const useMigration = (loadData, onMessage) => {
  const [isMigratingProductId, setIsMigratingProductId] = useState(null);
  const pollIntervalRef = useRef(null);

  // Очистка polling при размонтировании
  const cleanupPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const migrateProduct = useCallback(async (productId, targetPlatform, editedData = null) => {
    // Блокируем товар сразу на фронтенде
    setIsMigratingProductId(productId);
    onMessage?.(' Идет перенос товара...');

    try {
      const data = await api.migrateProduct(productId, targetPlatform, editedData);
      
      if (!data.success || !data.task_id) {
        throw new Error('Ошибка запуска миграции');
      }

      const platformName = targetPlatform;
      
      // Polling: проверяем статус задачи каждые 1 секунду
      pollIntervalRef.current = setInterval(async () => {
        try {
          const progress = await api.getTaskProgress(data.task_id);
          
          if (progress.status === 'completed' || progress.status === 'error') {
            cleanupPolling();
            setIsMigratingProductId(null);
            
            if (progress.status === 'completed') {
              onMessage?.(`✅ Товар успешно перенесён!`);
            } else {
              onMessage?.('❌ Ошибка при переносе товара');
            }
            
            loadData();
          }
        } catch (err) {
          cleanupPolling();
          setIsMigratingProductId(null);
          onMessage?.('❌ Ошибка проверки статуса задачи');
          loadData();
        }
      }, 1000);

      // Таймаут на случай зависания задачи (30 секунд)
      setTimeout(() => {
        cleanupPolling();
        setIsMigratingProductId(null);
        loadData();
      }, 30000);

      return data;
    } catch (err) {
      setIsMigratingProductId(null);
      onMessage?.('❌ ' + err.message);
      throw err;
    }
  }, [loadData, onMessage, cleanupPolling]);

  const migrateBatch = useCallback(async (productIds, targetPlatform) => {
    try {
      const data = await api.migrateBatch(productIds, targetPlatform);
      return data;
    } catch (err) {
      onMessage?.('❌ ' + err.message);
      throw err;
    }
  }, [onMessage]);

  const pollBatchProgress = useCallback((taskId, onProgress, onComplete) => {
    const interval = setInterval(async () => {
      try {
        const progress = await api.getTaskProgress(taskId);
        onProgress?.(progress);
        if (progress.status === 'completed' || progress.status === 'error') {
          clearInterval(interval);
          onComplete?.(progress);
          loadData();
        }
      } catch (err) {
        clearInterval(interval);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [loadData]);

  return {
    isMigratingProductId,
    migrateProduct,
    migrateBatch,
    pollBatchProgress,
    cleanupPolling
  };
};