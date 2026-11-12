import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDebouncedValue } from '../useDebouncedValue';

describe('useDebouncedValue', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('отдаёт начальное значение сразу, без задержки', () => {
    const { result } = renderHook(() => useDebouncedValue('товар', 300));
    expect(result.current).toBe('товар');
  });

  it('не обновляется до истечения задержки', () => {
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 300), {
      initialProps: { v: 'a' },
    });

    rerender({ v: 'ab' });
    expect(result.current).toBe('a');

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(result.current).toBe('a');

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe('ab');
  });

  it('схлопывает серию быстрых изменений в последнее значение', () => {
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 300), {
      initialProps: { v: '' },
    });

    // Печать слова «ноутбук» по символу, без пауз: каждый новый символ
    // сбрасывает таймер, поэтому задержанное значение не успевает обновиться
    let typed = '';
    for (const char of 'ноутбук') {
      typed += char;
      rerender({ v: typed });
      act(() => {
        vi.advanceTimersByTime(100);
      });
    }
    expect(result.current).toBe('');

    // Последний символ введён на t=600, его таймер сработает на t=900.
    // Часы на t=899 — до срабатывания ещё 1 мс, значение не отдано…
    act(() => {
      vi.advanceTimersByTime(199);
    });
    expect(result.current).toBe('');

    // …и сработал: отдано последнее значение, промежуточные потеряны
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe('ноутбук');
  });

  it('delay=0 обновляет значение на следующем тике', () => {
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 0), {
      initialProps: { v: 'x' },
    });

    rerender({ v: 'xy' });
    act(() => {
      vi.advanceTimersByTime(0);
    });
    expect(result.current).toBe('xy');
  });
});
