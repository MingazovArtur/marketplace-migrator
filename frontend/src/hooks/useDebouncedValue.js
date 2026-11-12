import { useEffect, useState } from 'react';

/**
 * Возвращает копию value, обновляющуюся не чаще, чем раз в `delay` мс.
 *
 * Задача — не дёргать сервер на каждый символ: в ProductsPage ввод
 * поиска мгновенно пишется в стейт (инпут не «залипает»), а в queryKey
 * уходит уже задержанное значение. 300 мс хватает, чтобы собрать слово,
 * и не хватает, чтобы пользователь заметил лаг результата.
 *
 * Классический паттерн «setTimeout + cleanup»: каждый новый рендер со
 * свежим value сбрасывает предыдущий таймер, поэтому до истечения задержки
 * учитывается только последнее значение.
 */
export const useDebouncedValue = (value, delay = 300) => {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    // Отрицательная/нулевая задержка не имеет смысла — отдаём значение сразу
    const effectiveDelay = delay > 0 ? delay : 0;
    const timer = setTimeout(() => setDebounced(value), effectiveDelay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
};
