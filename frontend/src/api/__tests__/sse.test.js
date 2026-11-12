/* Round 8: SSE-клиент api/sse.js.
 *
 * readSseStream: разбор кадров (в т.ч. разрезанных по чанкам), keepalive и
 * битый JSON не роняют поток, не-2xx — ошибка.
 * watchTask: терминальный кадр резолвит ожидание; SSE недоступен/пуст/сыпется —
 * тихий откат на polling-резерв; чистое закрытие потока без терминала —
 * переподключение; таймаут и отмена signal — ошибки.
 *
 * fetch подменяется стабом: ответ — { ok, status, body: ReadableStream },
 * этого достаточно (real Response не нужен и не везде есть в jsdom).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ReadableStream } from 'node:stream/web';
import { readSseStream, watchTask, isTerminalStatus } from '../sse';

const URL_SSE = 'http://localhost:8000/api/migrate/batch/task-1/events';

const sseResponse = (chunks, { status = 200 } = {}) => {
  const encoder = new TextEncoder();
  let i = 0;
  const body = new ReadableStream({
    pull(controller) {
      if (i < chunks.length) controller.enqueue(encoder.encode(chunks[i++]));
      else controller.close();
    },
  });
  return { ok: status >= 200 && status < 300, status, body };
};

/** Поток, который никогда не закрывается (для теста отмены). */
const endlessResponse = () => ({
  ok: true,
  status: 200,
  body: new ReadableStream({ start() {} }),
});

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('isTerminalStatus', () => {
  it('completed/failed — терминальные, остальное — нет', () => {
    expect(isTerminalStatus('completed')).toBe(true);
    expect(isTerminalStatus('failed')).toBe(true);
    expect(isTerminalStatus('pending')).toBe(false);
    expect(isTerminalStatus('progress')).toBe(false);
    expect(isTerminalStatus(undefined)).toBe(false);
  });
});

describe('readSseStream', () => {
  it('разбирает кадры, разрезанные по чанкам; keepalive игнорирует', async () => {
    const events = [];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          'data: {"status":"pend',
          'ing"}\n\n: keepalive\n\ndata: {"status":"progress","percent":',
          '50}\n\n',
        ])
      )
    );

    await readSseStream(URL_SSE, { onEvent: (p) => events.push(p) });

    expect(events).toEqual([{ status: 'pending' }, { status: 'progress', percent: 50 }]);
    // авторизация — как у всего API: cookie + CSRF-заголовок
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledWith(
      URL_SSE,
      expect.objectContaining({ credentials: 'include' })
    );
  });

  it('битый JSON не роняет поток: кадр пропускается, следующие читаются', async () => {
    const events = [];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse(['data: {broken json\n\n', 'data: {"status":"completed"}\n\n'])
      )
    );

    await readSseStream(URL_SSE, { onEvent: (p) => events.push(p) });

    expect(events).toEqual([{ status: 'completed' }]);
  });

  it('не-2xx — ошибка с кодом статуса', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([], { status: 502 })));

    await expect(readSseStream(URL_SSE, { onEvent: vi.fn() })).rejects.toThrow('HTTP 502');
  });
});

describe('watchTask', () => {
  it('резолвится терминальным кадром, polling-резерв не трогает', async () => {
    const events = [];
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        sseResponse([
          'data: {"status":"progress","done":1}\n\n',
          'data: {"status":"completed","done":2}\n\n',
        ])
      );
    const pollFallback = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const result = await watchTask(URL_SSE, {
      onEvent: (p) => events.push(p),
      pollFallback,
    });

    expect(result).toEqual({ status: 'completed', done: 2 });
    expect(events).toHaveLength(2); // терминальный кадр тоже приходит в onEvent
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(pollFallback).not.toHaveBeenCalled();
  });

  it('SSE недоступен — уходит в polling-резерв и резолвится терминалом', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
    const polls = [{ status: 'progress' }, { status: 'completed' }];
    const pollFallback = vi.fn(async () => polls.shift());
    const events = [];

    const p = watchTask(URL_SSE, {
      onEvent: (x) => events.push(x),
      pollFallback,
      pollIntervalMs: 1000,
    });
    const expectation = expect(p).resolves.toMatchObject({ status: 'completed' });
    await vi.advanceTimersByTimeAsync(2000);
    await expectation;

    expect(pollFallback).toHaveBeenCalledTimes(2);
    expect(events).toEqual([{ status: 'progress' }, { status: 'completed' }]);
  });

  it('пустой поток (закрылся без событий) — тоже уходит в резерв', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([]));
    vi.stubGlobal('fetch', fetchMock);
    const pollFallback = vi.fn(async () => ({ status: 'completed' }));

    const p = watchTask(URL_SSE, { onEvent: vi.fn(), pollFallback, pollIntervalMs: 500 });
    const expectation = expect(p).resolves.toMatchObject({ status: 'completed' });
    await vi.advanceTimersByTimeAsync(1000);
    await expectation;

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(pollFallback).toHaveBeenCalledTimes(1);
  });

  it('поток закрылся без терминала (лимит времени) — переподключается', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse(['data: {"status":"progress"}\n\n']))
      .mockResolvedValueOnce(sseResponse(['data: {"status":"completed"}\n\n']));
    vi.stubGlobal('fetch', fetchMock);

    const p = watchTask(URL_SSE, {
      onEvent: vi.fn(),
      pollFallback: vi.fn(),
      reconnectDelayMs: 100,
    });
    const expectation = expect(p).resolves.toMatchObject({ status: 'completed' });
    await vi.advanceTimersByTimeAsync(500);
    await expectation;

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('после 3 сбоев подряд уходит в polling-резерв', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse(['data: {"status":"progress"}\n\n']))
      .mockRejectedValue(new Error('network down'));
    vi.stubGlobal('fetch', fetchMock);
    const pollFallback = vi.fn(async () => ({ status: 'completed' }));
    const onError = vi.fn();

    const p = watchTask(URL_SSE, {
      onEvent: vi.fn(),
      onError,
      pollFallback,
      reconnectDelayMs: 100,
    });
    const expectation = expect(p).resolves.toMatchObject({ status: 'completed' });
    await vi.advanceTimersByTimeAsync(1000);
    await expectation;

    // 1 успешный поток + 3 сбоя подряд — и только потом резерв
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(pollFallback).toHaveBeenCalled();
    expect(onError).toHaveBeenCalled(); // потребитель узнал, что пошёл резерв
  });

  it('таймаут: SSE и резерв молчат дольше timeoutMs — timeoutMessage', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    const pollFallback = vi.fn(async () => ({ status: 'pending' }));

    const p = watchTask(URL_SSE, {
      onEvent: vi.fn(),
      pollFallback,
      timeoutMs: 5000,
      timeoutMessage: 'Таймаут ожидания (5 c)',
      pollIntervalMs: 1000,
    });
    const expectation = expect(p).rejects.toThrow('Таймаут ожидания (5 c)');
    await vi.advanceTimersByTimeAsync(6000);
    await expectation;
  });

  it('отмена signal рвёт ожидание, резервный polling не стартует', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(endlessResponse()));
    const pollFallback = vi.fn();

    const ac = new AbortController();
    const p = watchTask(URL_SSE, { onEvent: vi.fn(), pollFallback, signal: ac.signal });

    // дать fetch разрешиться и чтению потока начаться
    await new Promise((resolve) => setTimeout(resolve, 0));
    ac.abort();

    await expect(p).rejects.toThrow();
    expect(pollFallback).not.toHaveBeenCalled();
  });
});
