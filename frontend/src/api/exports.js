/* Экспорт: файлы для ЛК площадок, превью/валидация, эталонные шаблоны
 * (Р5: вынесено из api.js — секции «Export» и «Эталонные шаблоны площадок»). */

import {
  API_URL,
  doFetch,
  enc,
  extractErrorMessage,
  getAuthHeaders,
  getHeaders,
  parseContentDisposition,
  safeError,
} from './client';

export const exportApi = {
  exportForPlatform: async (platform, status = 'success', productIdOrIds = null) => {
    const q = new URLSearchParams();
    if (status) q.append('status', status);
    if (Array.isArray(productIdOrIds) && productIdOrIds.length > 0) {
      q.append('product_ids', productIdOrIds.join(','));
    } else if (productIdOrIds) {
      q.append('product_id', productIdOrIds);
    }
    const res = await doFetch(`${API_URL}/export/platform/${enc(platform)}?${q.toString()}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сформировать файл'));
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `upload_${platform}_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },

  exportPreview: async (
    platform,
    status = 'success',
    productIdOrIds = null,
    changedSince = false
  ) => {
    const q = new URLSearchParams();
    if (status) q.append('status', status);
    if (changedSince) q.append('changed_since', 'true');
    if (Array.isArray(productIdOrIds) && productIdOrIds.length > 0) {
      q.append('product_ids', productIdOrIds.join(','));
    } else if (productIdOrIds) {
      q.append('product_id', productIdOrIds);
    }
    const res = await doFetch(`${API_URL}/export/preview/${enc(platform)}?${q.toString()}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка предпросмотра выгрузки'));
    return res.json();
  },

  exportTemplate: async (platform) => {
    const res = await doFetch(`${API_URL}/export/template/${enc(platform)}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка скачивания шаблона'));
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

  exportReport: async () => {
    const res = await doFetch(`${API_URL}/export/report`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось сформировать отчет'));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `migration_report_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  validateExport: async (platform, status = 'all', productIdOrIds = null, changedSince = false) => {
    const q = new URLSearchParams();
    if (status) q.append('status', status);
    if (changedSince) q.append('changed_since', 'true');
    if (Array.isArray(productIdOrIds) && productIdOrIds.length > 0) {
      q.append('product_ids', productIdOrIds.join(','));
    } else if (productIdOrIds) {
      q.append('product_id', productIdOrIds);
    }
    const res = await doFetch(`${API_URL}/export/validate/${enc(platform)}?${q.toString()}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка проверки готовности к экспорту'));
    return res.json();
  },

  exportXlsxV2: async (
    platform,
    status = 'success',
    productIdOrIds = null,
    changedSince = false
  ) => {
    const q = new URLSearchParams();
    if (status) q.append('status', status);
    if (changedSince) q.append('changed_since', 'true');
    if (Array.isArray(productIdOrIds) && productIdOrIds.length > 0) {
      q.append('product_ids', productIdOrIds.join(','));
    } else if (productIdOrIds) {
      q.append('product_id', productIdOrIds);
    }

    const res = await doFetch(`${API_URL}/export/xlsx/${enc(platform)}?${q.toString()}`, {
      headers: getHeaders(),
    });

    if (!res.ok) {
      const msg = await safeError(res, 'Ошибка формирования XLSX');
      const isSingle = !Array.isArray(productIdOrIds) && productIdOrIds;
      throw new Error(
        isSingle
          ? `Товар #${productIdOrIds} не прошёл валидацию:\n\n${msg}`
          : `${msg}\n\nОткройте «Выгрузка» — блок валидации покажет, каких полей не хватает.`
      );
    }

    const blob = await res.blob();

    if (blob.type && blob.type.includes('application/json')) {
      const data = JSON.parse(await blob.text());
      throw new Error(extractErrorMessage(data, 'Ошибка формирования XLSX'));
    }

    const cd = res.headers.get('content-disposition');
    let filename = parseContentDisposition(cd, `${platform}_export.xlsx`);
    if (blob.type === 'application/zip' && !filename.toLowerCase().endsWith('.zip')) {
      filename = filename.replace(/\.xlsx$/i, '') + '.zip';
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return filename;
  },

  /* ---------- Эталонные шаблоны площадок ---------- */

  uploadOzonTemplate: async (categoryName, file, platform = 'ozon') => {
    const fd = new FormData();
    fd.append('category_name', categoryName);
    fd.append('platform', platform);
    fd.append('file', file);
    const res = await doFetch(`${API_URL}/export/ozon-template/upload`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: fd,
    });
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка загрузки эталонного шаблона'));
    return res.json();
  },

  listOzonTemplates: async (platform = 'ozon') => {
    const res = await doFetch(`${API_URL}/export/ozon-template/list?platform=${enc(platform)}`, {
      headers: getHeaders(),
    });
    if (!res.ok) return { templates: [] };
    return res.json();
  },

  listOzonTemplatesMeta: async () => {
    const res = await doFetch(`${API_URL}/export/ozon-template/meta`, { headers: getHeaders() });
    if (!res.ok) return { templates: [] };
    return res.json();
  },

  getOzonTemplateStatus: async (categoryName, platform = 'ozon') => {
    const res = await doFetch(
      `${API_URL}/export/ozon-template/status?category_name=${enc(categoryName)}&platform=${enc(platform)}`,
      { headers: getHeaders() }
    );
    if (!res.ok) return { has_official_template: false, meta: null };
    return res.json();
  },

  downloadOzonTemplate: async (categoryName, platform = 'ozon') => {
    const res = await doFetch(
      `${API_URL}/export/ozon-template/download?category_name=${enc(categoryName)}&platform=${enc(platform)}`,
      { headers: getHeaders() }
    );
    if (!res.ok) throw new Error(await safeError(res, 'Не удалось скачать эталон'));
    const blob = await res.blob();
    const filename = parseContentDisposition(
      res.headers.get('content-disposition'),
      `${platform}_template.xlsx`
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return filename;
  },

  deleteOzonTemplate: async (categoryName, platform = 'ozon') => {
    const res = await doFetch(
      `${API_URL}/export/ozon-template?category_name=${enc(categoryName)}&platform=${enc(platform)}`,
      {
        method: 'DELETE',
        headers: getHeaders(),
      }
    );
    if (!res.ok) throw new Error(await safeError(res, 'Ошибка удаления эталона'));
    return res.json();
  },
};
