import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

/* Конфиг Vitest отдельным файлом (а не блоком test в vite.config.js):
 * дев-прокси /api и /media из vite.config.js тестам не нужны, а смешивать
 * конфиги означает переустанавливать прокси при каждом расширении набора.
 *
 * environment: 'jsdom' — DOM для renderHook/render компонентов;
 * setupFiles — jest-dom-матчеры и act-окружение React 19 (src/test/setup.js).
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
  },
});
