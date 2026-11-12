import { describe, it, expect } from 'vitest';
import { extractErrorMessage, parseContentDisposition } from '../client';

describe('extractErrorMessage', () => {
  it('разворачивает fields из формата error_handler (field: message)', () => {
    const data = {
      error: {
        message: 'Ошибка валидации',
        details: { fields: [{ field: 'price', message: 'должна быть > 0' }] },
      },
    };
    expect(extractErrorMessage(data, 'fallback')).toBe('price: должна быть > 0');
  });

  it('берёт error.message, если нет полей', () => {
    expect(extractErrorMessage({ error: { message: 'нет доступа' } }, 'fb')).toBe('нет доступа');
  });

  it('разворачивает detail-массив FastAPI (loc — msg)', () => {
    const data = { detail: [{ loc: ['body', 'price'], msg: 'не число' }] };
    expect(extractErrorMessage(data, 'fb')).toBe('body.price — не число');
  });

  it('строковый detail возвращается как есть', () => {
    expect(extractErrorMessage({ detail: 'Товар не найден' }, 'fb')).toBe('Товар не найден');
  });

  it('объектный detail с message', () => {
    expect(extractErrorMessage({ detail: { message: 'токен истёк' } }, 'fb')).toBe('токен истёк');
  });

  it('null/пустой ответ → fallback', () => {
    expect(extractErrorMessage(null, 'fb')).toBe('fb');
    expect(extractErrorMessage({}, 'fb')).toBe('fb');
  });
});

describe('parseContentDisposition', () => {
  it('приоритет filename* (RFC 5987, кириллица)', () => {
    const header = `attachment; filename="export.xlsx"; filename*=UTF-8''${encodeURIComponent(
      'Выгрузка-озон.xlsx'
    )}`;
    expect(parseContentDisposition(header)).toBe('Выгрузка-озон.xlsx');
  });

  it('quoted filename', () => {
    expect(parseContentDisposition('attachment; filename="report 2026.xlsx"')).toBe(
      'report 2026.xlsx'
    );
  });

  it('plain filename без кавычек', () => {
    expect(parseContentDisposition('attachment; filename=ozon.xlsx; size=123')).toBe('ozon.xlsx');
  });

  it('битый filename* (некорректный percent-encoding) не роняет парсер', () => {
    expect(parseContentDisposition(`attachment; filename*=UTF-8''%zz%`)).toBe('export.xlsx');
  });

  it('нет заголовка → fallback', () => {
    expect(parseContentDisposition(null, 'mega.xlsx')).toBe('mega.xlsx');
  });
});
