/**
 * Единая точка логирования фронтенда.
 * Диагностика из catch-блоков (ошибки сети/БД/валидации) идёт через logger,
 * а не через console напрямую: правило no-console действует на весь src/,
 * кроме этого файла — здесь console инкапсулирован (единое место, чтобы
 * позже добавить уровни/телеметрию, не трогая точки вызова).
 */
/* eslint-disable no-console */
export const logger = {
  error: (...args) => console.error(...args),
  warn: (...args) => console.warn(...args),
};
