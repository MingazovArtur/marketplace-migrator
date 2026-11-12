/* Импорт товаров: по API-ключу и из файла
 * (Р5: вынесено из api.js — секция «Import»). */

import { API_URL, doFetch, enc, getAuthHeaders, getHeaders, safeError } from './client';

export const importApi = {
  importProducts: async (authKey) => {
    const res = await doFetch(`${API_URL}/import`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ key: authKey, full_key: authKey, auth_key: authKey }),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка импорта'));
    return res.json();
  },

  previewFileImport: async (platform, file) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('platform', platform);
    const res = await doFetch(`${API_URL}/import/preview`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: fd,
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось прочитать файл'));
    return res.json();
  },

  downloadImportTemplate: async (platform) => {
    const res = await doFetch(`${API_URL}/templates/${enc(platform)}`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Шаблон не найден'));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `template_${platform}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  importFromFile: async (platform, file, mode = 'create') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('platform', platform);
    formData.append('mode', mode);
    const res = await doFetch(`${API_URL}/import/file`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки файла'));
    return res.json();
  },
};
