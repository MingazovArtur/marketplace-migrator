import { useState, useCallback, useRef } from 'react';
import { api } from '../api';

export const useMigration = (loadData, onMessage) => {
  const [isMigratingProductId, setIsMigratingProductId] = useState(null);
  const pollIntervalRef = useRef(null);

  // Очистка polling одиночной миграции
  const cleanupPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  // =====================================================================
  // ОДИНОЧНАЯ МИГРАЦИЯ (polling внутри хука)
  // =====================================================================
  const migrateProduct = useCallback(async (productId, targetPlatform, editedData = null) => {
    setIsMigratingProductId(productId);
    onMessage?.('⏳ Идет перенос товара...');

    try {
      const data = await api.migrateProduct(productId, targetPlatform, editedData);

      if (!data.success || !data.task_id) {
        throw new Error('Ошибка запуска миграции');
      }

      // Polling статуса задачи
      pollIntervalRef.current = setInterval(async () => {
        try {
          const progress = await api.getTaskProgress(data.task_id);

          if (
            progress.status === 'completed' ||
            progress.status === 'failed' ||
            progress.status === 'error'
          ) {
            cleanupPolling();
            setIsMigratingProductId(null);

            if (progress.status === 'completed') {
              onMessage?.('✅ Товар успешно перенесён!');
            } else {
              onMessage?.('❌ Ошибка при переносе товара: ' + (progress.error || ''));
            }
            loadData();
          }
        } catch (err) {
          cleanupPolling();
          setIsMigratingProductId(null);
          onMessage?.('❌ Ошибка проверки статуса задачи');
          loadData();
        }
      }, 1500);

      // Страховочный таймаут (60 сек)
      setTimeout(() => {
        cleanupPolling();
        setIsMigratingProductId(null);
        loadData();
      }, 60000);

      return data;
    } catch (err) {
      setIsMigratingProductId(null);
      onMessage?.('❌ ' + err.message);
      throw err;
    }
  }, [loadData, onMessage, cleanupPolling]);

  // =====================================================================
  // ПАКЕТНАЯ МИГРАЦИЯ (просто старт — возвращает {batch_id, total})
  // Polling прогресса делает сама BatchMigrateModal через pollBatchProgress
  // =====================================================================
  const migrateBatch = useCallback(async (productIds, targetPlatform) => {
    const data = await api.migrateBatch(productIds, targetPlatform);
    // ✅ принимаем batch_id / task_id / id — что вернул сервер
    const batchId = data?.batch_id || data?.task_id || data?.id;
    if (!batchId) {
      throw new Error('Сервер не вернул ID задачи. Ответ: ' + JSON.stringify(data).slice(0, 150));
    }
    return { ...data, batch_id: batchId };
  }, []);

  // =====================================================================
  // ПОЛУЧЕНИЕ ПРОГРЕССА ПАКЕТНОЙ МИГРАЦИИ
  // Используется в BatchMigrateModal через await pollProgress(batchId)
  // Это простая async-функция — без interval внутри
  // =====================================================================
  const pollBatchProgress = useCallback(async (taskId) => {
    return await api.getTaskProgress(taskId);
  }, []);

  return {
    isMigratingProductId,
    migrateProduct,
    migrateBatch,
    pollBatchProgress,
    cleanupPolling,
  };
};