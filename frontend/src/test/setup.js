/* Глобальный setup для Vitest (подключается из vitest.config.js).
 *
 * 1. jest-dom добавляет матчеры к DOM-нодовам (toBeDisabled, toBeVisible…);
 *    вход именно `/vitest` — матчеры регистрируются на expect из Vitest.
 * 2. React 19 + testing-library: act-окружение должно быть включено явно,
 *    иначе рендер/обновления в тестах падают с предупреждением act().
 * 3. Авто-cleanup RTL включается только при глобальном test-фреймворке
 *    (globals: true); у нас импорты из 'vitest' явные — значит, чистим DOM
 *    сами, иначе рендеры накапливаются между тестами файла.
 */
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  cleanup();
});
