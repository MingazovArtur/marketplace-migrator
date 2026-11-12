/* Общий HTTP-клиент API (Р5: вынесено из api.js).
 * Все доменные модули пакета src/api/ строятся на этих примитивах. */

export const API_URL =
  import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '/api' : 'http://localhost:8000/api');

// Все динамические сегменты пути (кириллица, пробелы, «→») обязаны кодироваться
export const enc = encodeURIComponent;

/* ---------- Аутентификация (cookie-based) ----------
 * Токен живёт в httpOnly-куке access_token (JS не читает — защита от XSS).
 * Все запросы идут с credentials: 'include' (в проде same-origin, в dev — CORS).
 * Мутации дополнительно подписываются CSRF-заголовком (double-submit).
 */
const getCsrfToken = () =>
  document.cookie
    .split('; ')
    .find((c) => c.startsWith('csrf_token='))
    ?.split('=')[1] || '';

const csrfHeaders = () => ({ 'X-CSRF-Token': getCsrfToken() });

export const getHeaders = () => ({
  'Content-Type': 'application/json',
  ...csrfHeaders(),
});

export const getAuthHeaders = () => ({ ...csrfHeaders() });

// fetch с куками (единая точка)
export const doFetch = (url, options = {}) => fetch(url, { credentials: 'include', ...options });

export function extractErrorMessage(data, fallback) {
  if (!data) return fallback;

  // 1. Формат централизованного обработчика backend/core/error_handler.py
  if (data.error && typeof data.error === 'object') {
    const fields = data.error.details?.fields;
    if (Array.isArray(fields) && fields.length > 0) {
      return fields.map((f) => `${f.field}: ${f.message}`).join('; ');
    }
    if (typeof data.error.message === 'string' && data.error.message) {
      return data.error.message;
    }
  }

  // 2. Стандартный формат FastAPI HTTPException / ValidationError
  if (data.detail) {
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => `${(d.loc || []).join('.')} — ${d.msg}`).join('; ');
    }
    if (typeof data.detail === 'object') {
      if (data.detail.message) return data.detail.message;
      return JSON.stringify(data.detail);
    }
    return String(data.detail);
  }

  return data.message || fallback;
}

export async function safeError(res, fallback) {
  try {
    const data = await res.json();
    return extractErrorMessage(data, fallback);
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
}

/**
 * Извлечь имя файла из Content-Disposition (RFC 5987):
 * приоритет filename*=UTF-8''... (кириллица), затем filename="...".
 */
export const parseContentDisposition = (header, fallback = 'export.xlsx') => {
  if (!header) return fallback;
  const utf8Match = header.match(/filename\*\s*=\s*UTF-8''([^;\s]+)/i);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      /* fallthrough */
    }
  }
  const quotedMatch = header.match(/filename\s*=\s*"([^"]+)"/i);
  if (quotedMatch) return quotedMatch[1];
  const plainMatch = header.match(/filename\s*=\s*([^;\s]+)/i);
  if (plainMatch) return plainMatch[1];
  return fallback;
};
