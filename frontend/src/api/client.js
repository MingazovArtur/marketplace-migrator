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
 * Имена кук (access_token / csrf_token) продублированы константами в
 * backend/core/auth.py — синхронность обеспечивают тесты test_cookie_auth.py.
 */
// Берём ПЕРВУЮ куку csrf_token: пока приложение живёт на одном домене,
// других не бывает. Если появятся поддомены с собственными csrf_token —
// уточнить выбор по path/domain (R35, замечание ревью).
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

/* ---------- Централизованная обработка 401 (R30, С-3 ревью) ----------
 * Истёкшая/отозванная кука access_token раньше оставляла пользователя в
 * «залогиненном» UI: каждый запрос сыпал ошибками, пока не перезагрузишь
 * страницу. Теперь doFetch при 401 на любом НЕ-auth эндпоинте диспатчит
 * window-событие 'auth:expired'; App по нему выходит из залогиненного
 * режима и открывает модалку входа (см. App.jsx).
 * Событие, а не прямой вызов — client.js остаётся низкоуровневым,
 * без зависимости от React-кода и циклических импортов.
 *
 * /api/auth/* — исключение: 401 там — штатный ответ («неверный пароль»,
 * «не вошли»), а не истечение сессии.
 */
const AUTH_URL_PREFIX = `${API_URL}/auth/`;

export async function doFetch(url, options = {}) {
  const res = await fetch(url, { credentials: 'include', ...options });
  if (res.status === 401 && !url.startsWith(AUTH_URL_PREFIX)) {
    window.dispatchEvent(new CustomEvent('auth:expired', { detail: { url } }));
  }
  return res;
}

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
