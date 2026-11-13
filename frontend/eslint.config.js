// Flat config (ESLint 9): миграция 1:1 с .eslintrc.json (Round 25).
// Начиная с ESLint 9 по умолчанию (а с 10 — единственный формат)
// используется flat config; eslintrc-файлы больше не читаются. Здесь
// тот же набор правил, что был в .eslintrc.json до миграции.
//
// ESLint держим на 9.x (не 10.x): последний eslint-plugin-react 7.37.5
// не поддерживает ESLint 10 (peer ^9.7, detect-путь падает на удалённом
// context.getFilename()) — мерж dependabot-PR eslint-10 сломал бы npm ci
// и линт. Когда плагин выпустит поддержку 10.x — поднимем минорным
// раундом (правило preserve-caught-error из recommended 10 уже
// учтено в плане — см. docs/engineering.md, §1).
//
// Отличие от простой миграции: eslint-plugin-react-hooks 7 расширил
// recommended-пресет compiler-правилами (purity, immutability, refs и др. —
// 15 новых правил в error). Чтобы обновление зависимостей НЕ меняло набор
// проверок, подключены только правила пресета v5 (rules-of-hooks error,
// exhaustive-deps warn); включение compiler-правил v7 — отдельная линия
// долга с анализом каждого замечания (см. docs/engineering.md, §1).

import js from '@eslint/js';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettier from 'eslint-config-prettier';
import globals from 'globals';

export default [
  // эквивалент extends: eslint:recommended, plugin:react/recommended
  js.configs.recommended,
  react.configs.flat.recommended,
  // "prettier" последним: выключает правила, конфликтующие с prettier
  prettier,

  {
    // env: browser + es2021 + node (es2021 покрывается ecmaVersion: latest)
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node },
    },
    // react подключён конфигом выше; react-hooks — вручную (v5-набор правил);
    // react-refresh не имеет recommended-пресета
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    settings: { react: { version: 'detect' } },
    rules: {
      // v5-набор plugin:react-hooks/recommended (без compiler-правил v7)
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      // как в .eslintrc.json
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'no-unused-vars': 'warn',
      'no-console': 'warn',
    },
  },
];
