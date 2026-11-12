import { useState, useCallback } from 'react';
import { api } from '../api';

/**
 * Хук для управления миграцией товаров.
 *
 * ✅ v3:
 *   - migrateProduct возвращает Promise после завершения Celery-задачи
 *   - migrateBatchWithExport: пакетная миграция + авто-экспорт всех успешных товаров
 *   - Обработка ZIP (несколько категорий) и ошибок экспорта
 *
 * ✅ Round 8: ожидание задачи — SSE-поток (api.streamTaskProgress);
 * polling — автоматический резерв внутри api/sse.js (при сбое SSE).
 */
export const useMigration = (loadData, onMessage) => {
  const [isMigratingProductId, setIsMigratingProductId] = useState(null);

  // =====================================================================
  // Ожидание завершения Celery-задачи: SSE-пуш, polling — резерв
  // =====================================================================
  const pollUntilDone = useCallback(async (taskId, maxAttempts = 90) => {
    try {
      const progress = await api.streamTaskProgress(taskId, {
        timeoutMs: maxAttempts * 1000,
        timeoutMessage: `Таймаут ожидания миграции (${maxAttempts} сек). Проверьте логи Celery.`,
      });

      if (progress.status === 'completed') {
        return { status: 'completed', progress };
      }
      return {
        status: 'failed',
        error: progress.error || progress.message || 'Миграция завершилась с ошибкой',
        progress,
      };
    } catch (err) {
      return {
        status: 'failed',
        error: `Не удалось получить прогресс задачи: ${err.message}`,
      };
    }
  }, []);

  // =====================================================================
  // ОДИНОЧНАЯ МИГРАЦИЯ (Promise резолвится по завершении задачи)
  // =====================================================================
  const migrateProduct = useCallback(
    async (productId, targetPlatform, editedData = null) => {
      setIsMigratingProductId(productId);
      onMessage?.('⏳ Идет перенос товара...');

      try {
        const startResult = await api.migrateProduct(productId, targetPlatform, editedData);

        if (!startResult.success && !startResult.task_id) {
          throw new Error(
            'Сервер не запустил задачу миграции: ' + JSON.stringify(startResult).slice(0, 200)
          );
        }

        const taskId = startResult.task_id;
        if (!taskId) {
          setIsMigratingProductId(null);
          loadData?.();
          onMessage?.('✅ Товар успешно перенесён!');
          return startResult;
        }

        const result = await pollUntilDone(taskId);

        setIsMigratingProductId(null);
        loadData?.();

        if (result.status === 'completed') {
          onMessage?.('✅ Товар успешно перенесён!');
          return result.progress;
        }

        throw new Error(result.error);
      } catch (err) {
        setIsMigratingProductId(null);
        loadData?.();
        onMessage?.('❌ ' + err.message);
        throw err;
      }
    },
    [loadData, onMessage, pollUntilDone]
  );

  // =====================================================================
  // ПАКЕТНАЯ МИГРАЦИЯ (просто старт — возвращает {batch_id, total})
  // =====================================================================
  const migrateBatch = useCallback(async (productIds, targetPlatform) => {
    const data = await api.migrateBatch(productIds, targetPlatform);
    const batchId = data?.batch_id || data?.task_id || data?.id;
    if (!batchId) {
      throw new Error('Сервер не вернул ID задачи. Ответ: ' + JSON.stringify(data).slice(0, 150));
    }
    return { ...data, batch_id: batchId };
  }, []);

  // =====================================================================
  // ✅ ПАКЕТНАЯ МИГРАЦИЯ + АВТО-ЭКСПОРТ (для "Мигрировать выбранные")
  // =====================================================================
  const migrateBatchWithExport = useCallback(
    async (productIds, targetPlatform) => {
      onMessage?.(`⏳ Запускаем пакетную миграцию ${productIds.length} товаров...`);

      // 1. Старт пакетной миграции
      const batchData = await migrateBatch(productIds, targetPlatform);
      const batchId = batchData.batch_id;

      onMessage?.(`⏳ Миграция запущена (batch_id: ${batchId}). Ожидаем завершения...`);

      // 2. Polling до завершения (до 5 минут для больших пакетов)
      const result = await pollUntilDone(batchId, 300);

      loadData?.();

      if (result.status === 'failed') {
        throw new Error(result.error);
      }

      // 3. Миграция завершена — скачиваем файл ВСЕХ успешных товаров
      const progress = result.progress || {};
      const successCount = progress.success || 0;
      const errorCount = progress.errors || 0;

      if (successCount === 0) {
        onMessage?.(
          `⚠️ Пакетная миграция завершена, но все ${errorCount} товаров отклонены. ` +
            `Проверьте цены, категории и обязательные поля.`
        );
        return { success: 0, errors: errorCount, filename: null };
      }

      onMessage?.(
        `✅ Миграция завершена (${successCount}/${productIds.length} успешно). Скачиваем файл...`
      );

      try {
        // ✅ Вызов экспорта БЕЗ product_id — скачиваем ВСЕ успешные товары
        const filename = await api.exportXlsxV2(targetPlatform, 'success');

        // Определение ZIP (несколько категорий)
        if (filename.endsWith('.zip')) {
          onMessage?.(
            `⚠️ Скачан ZIP-архив: товары лежат в разных категориях, у каждой свой шаблон.\n\n` +
              `📦 Распакуйте архив и загружайте каждый XLSX отдельно в кабинете ${targetPlatform}.\n` +
              `✅ Миграция: ${successCount} успешно, ${errorCount} с ошибками.`
          );
        } else {
          onMessage?.(
            `✅ Пакетная миграция завершена. Файл «${filename}» скачан.\n` +
              `📊 Успешно: ${successCount}, с ошибками: ${errorCount}.\n\n` +
              `Загрузите файл в кабинете ${targetPlatform}.`
          );
        }

        return { success: successCount, errors: errorCount, filename };
      } catch (exportErr) {
        // Экспорт не удался — миграция прошла, но файл не сформирован
        onMessage?.(
          `✅ Пакетная миграция завершена (${successCount} успешно, ${errorCount} с ошибками), ` +
            `но файл не сформирован: ${exportErr.message}\n\n` +
            `Откройте «Выгрузка» — там видно, каким товарам чего не хватает.`
        );
        return {
          success: successCount,
          errors: errorCount,
          filename: null,
          exportError: exportErr.message,
        };
      }
    },
    [migrateBatch, pollUntilDone, loadData, onMessage]
  );

  // =====================================================================
  // ПОЛУЧЕНИЕ ПРОГРЕССА ПАКЕТНОЙ МИГРАЦИИ: не нужно — BatchMigrateModal
  // читает SSE-поток напрямую (api.streamTaskProgress, Round 8)
  // =====================================================================

  return {
    isMigratingProductId,
    migrateProduct,
    migrateBatch,
    migrateBatchWithExport, // ✅ новый метод
  };
};
