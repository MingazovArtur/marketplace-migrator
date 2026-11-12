/* Агрегатор API (Р5: монолит src/api.js, 1016 строк / 79 методов, разбит на
 * доменные модули — client, auth, products, migration, categories, imports,
 * exports, defaults, stats, specs).
 *
 * Публичный API сохранён без изменений: `import { api } from '../api'`
 * резолвится в этот файл, все имена методов и сигнатуры те же, `API_URL`
 * по-прежнему экспортируется (нужен PhotosModal.jsx).
 */

import { authApi } from './auth';
import { categoriesApi } from './categories';
import { defaultsApi } from './defaults';
import { exportApi } from './exports';
import { importApi } from './imports';
import { migrationApi } from './migration';
import { productsApi } from './products';
import { specsApi } from './specs';
import { statsApi } from './stats';

export { API_URL } from './client';

export const api = {
  ...authApi,
  ...productsApi,
  ...migrationApi,
  ...categoriesApi,
  ...importApi,
  ...exportApi,
  ...defaultsApi,
  ...statsApi,
  ...specsApi,
};
