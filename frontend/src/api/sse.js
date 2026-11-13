/* SSE-клиент (Round 8): push-прогресс фоновых задач вместо polling'а.
 *
 * Почему не EventSource: он не отправляет наши заголовки (CSRF) и не даёт
 * управлять credentials так, как весь остальной API (httpOnly-cookie).
 * Поток читаем через fetch + ReadableStream — авторизация идентична
 * остальным запросам (credentials: 'include', X-CSRF-Token).
 *
 * Каркас потребителя — watchTask:
 *   1) SSE-поток с автопереподключением: сервер сам закрывает поток по
 *      лимиту времени (backend/core/sse.py MAX_STREAM_SECONDS) — это норма,
 *      подключаемся заново; терминальный кадр (completed/failed/…) закрывает
 *      ожидание — promise резолвится этим кадром;
 *   2) если SSE не заработал вовсе (старый прокси режет стрим, нет тела
 *      ответа) или сеть сыпется 3 раза подряд — тихий откат на polling
 *      по старым эндпоинтам /progress: они остаются рабочим резервом;
 *   3) timeoutMs — общий потолок ожидания (SSE + резервный polling вместе).
 */

import { doFetch, getAuthHeaders } from './client';

export const TERMINAL_TASK_STATUSES = ['completed', 'failed'];

export const isTerminalStatus = (status, terminal = TERMINAL_TASK_STATUSES) =>
  terminal.includes(status);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));

const makeAbortError = () =>
  typeof DOMException !== 'undefined'
    ? new DOMException('Aborted', 'AbortError')
    : new Error('Aborted');

/**
 * Читает один SSE-поток до его закрытия сервером.
 *
 * onEvent вызывается для каждого data-кадра (JSON). Комментарии (keepalive)
 * и пустые кадры игнорируются, битый JSON не роняет поток. Бросает при
 * сетевой ошибке/не-2xx/отмене — решение «переподключиться или уйти в
 * polling» принимает watchTask.
 */
export async function readSseStream(url, { onEvent, signal, headers } = {}) {
  const res = await doFetch(url, {
    headers: { Accept: 'text/event-stream', ...getAuthHeaders(), ...headers },
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  if (!res.body) throw new Error('SSE не поддерживается (пустое тело ответа)');

  // Отмена должна рвать чтение даже там, где fetch не прокидывает signal
  // в body-stream: гоняем reader.read() с abort-промисом.
  let onAbort = null;
  const abortPromise = signal
    ? new Promise((_, reject) => {
        onAbort = () => reject(makeAbortError());
        if (signal.aborted) onAbort();
        else signal.addEventListener('abort', onAbort, { once: true });
      })
    : null;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const emitFrames = () => {
    // кадр — строки до пустой строки; нормализуем CRLF (на всякий случай:
    // наш бэкенд шлёт \n, но прокси теоретически может пере-разбить)
    buffer = buffer.replace(/\r\n/g, '\n');
    let sep = buffer.indexOf('\n\n');
    while (sep >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      sep = buffer.indexOf('\n\n');

      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('\n');
      if (!data) continue; // keepalive-комментарий или пустой кадр
      try {
        onEvent(JSON.parse(data));
      } catch {
        console.warn('SSE: не разобран кадр', data.slice(0, 100));
      }
    }
  };

  try {
    for (;;) {
      const read = reader.read();
      const { done, value } = await (abortPromise ? Promise.race([read, abortPromise]) : read);
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      emitFrames();
    }
  } finally {
    if (onAbort && signal && !signal.aborted) {
      signal.removeEventListener('abort', onAbort);
    }
    // читатель больше не нужен (поток кончился или отмена) — освобождаем
    reader.cancel?.().catch?.(() => {});
  }
}

/**
 * Следит за задачей: SSE-поток с автопереподключением; при недоступности
 * SSE — polling-резерв. Promise резолвится терминальным кадром (onEvent для
 * него тоже вызывается), rejecting — по таймауту/отмене signal.
 *
 * @param {string} url SSE-эндпоинт
 * @param {object} opts
 *   onEvent(payload)     каждый кадр, включая терминальный
 *   onError(err)         уведомление о сбоях: SSE сдался → резерв, попытка
 *                        резервного polling'а не удалась
 *   pollFallback()       async () => payload (старый polling-эндпоинт)
 *   isTerminal(payload)  терминален ли кадр (по умолчанию completed/failed)
 *   timeoutMs            общий потолок ожидания (по умолчанию — бессрочно)
 *   timeoutMessage       текст ошибки таймаута
 *   pollIntervalMs       интервал резервного polling'а (default 1000)
 *   reconnectDelayMs     пауза между переподключениями SSE (default 1000)
 *   signal               AbortSignal — отмена (unmount/закрытие модалки)
 */
export async function watchTask(url, opts = {}) {
  const {
    onEvent,
    onError,
    pollFallback,
    isTerminal = (p) => isTerminalStatus(p?.status),
    timeoutMs = Infinity,
    timeoutMessage = 'Превышено время ожидания задачи',
    pollIntervalMs = 1000,
    reconnectDelayMs = 1000,
    signal,
  } = opts;

  const deadline = Date.now() + timeoutMs;
  let terminalPayload = null;
  let seenAnyEvent = false;
  let consecutiveFailures = 0;
  let timedOut = false;
  let lastError = null;

  // Внутренний AbortController: рвёт SSE-поток по таймауту; внешний signal
  // тоже пробрасывается внутрь (отмена пользователем/при размонтировании)
  const internal = new AbortController();
  const onOuterAbort = () => internal.abort();
  if (signal) {
    if (signal.aborted) internal.abort();
    else signal.addEventListener('abort', onOuterAbort, { once: true });
  }
  let timeoutId = null;
  if (Number.isFinite(deadline)) {
    timeoutId = setTimeout(
      () => {
        timedOut = true;
        internal.abort();
      },
      Math.max(0, deadline - Date.now())
    );
  }

  const handleEvent = (payload) => {
    seenAnyEvent = true;
    consecutiveFailures = 0;
    onEvent?.(payload);
    if (isTerminal(payload)) terminalPayload = payload;
  };

  try {
    // --- фаза 1: SSE с автопереподключением ---
    while (!terminalPayload && Date.now() < deadline) {
      try {
        await readSseStream(url, { onEvent: handleEvent, signal: internal.signal });
        // сервер закрыл поток: терминал — готово; пустой поток — SSE у нас
        // не работает, уходим в резерв; иначе (лимит времени потока) — заново
        if (terminalPayload || !seenAnyEvent) break;
        await sleep(reconnectDelayMs);
      } catch (err) {
        if (signal?.aborted) throw err;
        if (timedOut) throw new Error(timeoutMessage);
        lastError = err;
        if (!seenAnyEvent) break; // SSE не заработал вовсе → polling-резерв
        consecutiveFailures += 1;
        if (consecutiveFailures >= 3) break; // сеть сыпется → polling-резерв
        await sleep(reconnectDelayMs);
      }
    }

    if (terminalPayload) return terminalPayload;
    if (signal?.aborted) throw makeAbortError();
    if (timedOut || Date.now() >= deadline) throw new Error(timeoutMessage);

    // --- фаза 2: polling-резерв (SSE недоступен, старые эндпоинты живы) ---
    if (typeof pollFallback !== 'function') {
      throw lastError instanceof Error ? lastError : new Error('SSE недоступен');
    }
    if (lastError === null) lastError = new Error('SSE недоступен');
    onError?.(lastError);
    while (Date.now() < deadline) {
      let payload = null;
      try {
        payload = await pollFallback();
      } catch (err) {
        if (signal?.aborted) throw err;
        onError?.(err); // разовый сбой — покажем и попробуем ещё раз
      }
      if (payload) {
        handleEvent(payload);
        if (terminalPayload) return terminalPayload;
      }
      await sleep(pollIntervalMs);
    }
    throw new Error(timeoutMessage);
  } finally {
    if (timeoutId !== null) clearTimeout(timeoutId);
    if (signal) signal.removeEventListener('abort', onOuterAbort);
    internal.abort(); // подчищаем висящее чтение, если promise уже решён
  }
}
