import { useState, useCallback } from 'react';
import { api } from '../api';

/**
 * Хук для управления миграцией товаров.
 *
 * ✅ Исправлено:
 *   - migrateProduct теперь ВОЗВРАЩАЕТ Promise, который резолвится
 *     ТОЛЬКО ПОСЛЕ завершения Celery-задачи (устранён race condition с экспортом)
 *   - polling реализован через async/await цикл (без setInterval)
 *   - убран страховочный setTimeout — заменён maxAttempts
 *   - сохранена обратная совместимость с BatchMigrateModal
 */
export const useMigration = (loadData, onMessage) => {
  const [isMigratingProductId, setIsMigratingProductId] = useState(null);

  // =====================================================================
  // Внутренний polling: ждёт завершения Celery-задачи
  // =====================================================================
  const pollUntilDone = useCallback(async (taskId, maxAttempts = 90) => {
    // 90 попыток × 1 сек = до 90 секунд ожидания
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 1000));

      try {
        const progress = await api.getTaskProgress(taskId);

        if (progress.status === 'completed') {
          return { status: 'completed', progress };
        }
        if (progress.status === 'failed' || progress.status === 'error') {
          return {
            status: 'failed',
            error: progress.error || progress.message || 'Миграция завершилась с ошибкой',
            progress,
          };
        }
        // status === 'pending' / 'progress' — продолжаем polling
      } catch (err) {
        // Сетевая ошибка — не прерываем цикл, пробуем ещё раз
        if (attempt >= maxAttempts) {
          return {
            status: 'failed',
            error: `Не удалось получить прогресс задачи: ${err.message}`,
          };
        }
      }
    }

    // Таймаут
    return {
      status: 'failed',
      error: 'Таймаут ожидания миграции (90 сек). Проверьте логи Celery.',
    };
  }, []);

  // =====================================================================
  // ОДИНОЧНАЯ МИГРАЦИЯ (Promise резолвится по завершении задачи)
  // =====================================================================
  const migrateProduct = useCallback(async (productId, targetPlatform, editedData = null) => {
    setIsMigratingProductId(productId);
    onMessage?.('⏳ Идет перенос товара...');

    try {
      // 1. Старт задачи в Celery
      const startResult = await api.migrateProduct(productId, targetPlatform, editedData);

      if (!startResult.success && !startResult.task_id) {
        throw new Error(
          'Сервер не запустил задачу миграции: ' +
            JSON.stringify(startResult).slice(0, 200)
        );
      }

      const taskId = startResult.task_id;
      if (!taskId) {
        // Старое синхронное API — считаем выполненным
        setIsMigratingProductId(null);
        loadData?.();
        onMessage?.('✅ Товар успешно перенесён!');
        return startResult;
      }

      // 2. Ждём завершения задачи (до 90 сек)
      const result = await pollUntilDone(taskId);

      setIsMigratingProductId(null);
      loadData?.();

      if (result.status === 'completed') {
        onMessage?.('✅ Товар успешно перенесён!');
        return result.progress;  // ← возвращаем финальный прогресс
      }

      // Ошибка — пробрасываем дальше, чтобы App.jsx мог поймать и показать
      throw new Error(result.error);
    } catch (err) {
      setIsMigratingProductId(null);
      loadData?.();
      onMessage?.('❌ ' + err.message);
      throw err;  // ← пробрасываем — App.jsx решит, вызывать ли экспорт
    }
  }, [loadData, onMessage, pollUntilDone]);

  // =====================================================================
  // ПАКЕТНАЯ МИГРАЦИЯ (просто старт — возвращает {batch_id, total})
  // Polling прогресса делает сама BatchMigrateModal через pollBatchProgress
  // =====================================================================
  const migrateBatch = useCallback(async (productIds, targetPlatform) => {
    const data = await api.migrateBatch(productIds, targetPlatform);
    const batchId = data?.batch_id || data?.task_id || data?.id;
    if (!batchId) {
      throw new Error(
        'Сервер не вернул ID задачи. Ответ: ' + JSON.stringify(data).slice(0, 150)
      );
    }
    return { ...data, batch_id: batchId };
  }, []);

  // =====================================================================
  // ПОЛУЧЕНИЕ ПРОГРЕССА ПАКЕТНОЙ МИГРАЦИИ (один запрос)
  // Используется в BatchMigrateModal через await pollBatchProgress(batchId)
  // =====================================================================
  const pollBatchProgress = useCallback(async (taskId) => {
    return await api.getTaskProgress(taskId);
  }, []);

  // =====================================================================
  // Cleanup (оставлен для обратной совместимости — теперь no-op)
  // =====================================================================
  const cleanupPolling = useCallback(() => {
    // polling теперь внутри async-цикла — внешнего interval нет
  }, []);

  return {
    isMigratingProductId,
    migrateProduct,
    migrateBatch,
    pollBatchProgress,
    cleanupPolling,
  };
};