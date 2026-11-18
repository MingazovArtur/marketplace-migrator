import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import React from 'react';
import FirstMigrationWizard from './FirstMigrationWizard';

/* Тесты мастера первой миграции. Мокаем агрегатор api — мастеру нужны
 * previewFileImport/importFromFile/importProducts (шаг «Откуда»),
 * getProducts/getGaps (сводка после импорта), migrateBatch +
 * streamTaskProgress (SSE-прогресс), exportXlsxV2 (финальный XLSX). */
vi.mock('../../api', () => ({
  api: {
    previewFileImport: vi.fn(),
    importFromFile: vi.fn(),
    importProducts: vi.fn(),
    getProducts: vi.fn(),
    getGaps: vi.fn(),
    migrateBatch: vi.fn(),
    streamTaskProgress: vi.fn(),
    exportXlsxV2: vi.fn(),
  },
}));

import { api } from '../../api';

const PRODUCTS = [
  { id: 1, title: 'Худи oversize', price: 2490, photos: ['x'] },
  { id: 2, title: 'Футболка', price: 890, photos: ['x'] },
];

const renderWizard = (props = {}) =>
  render(
    <FirstMigrationWizard
      isOpen
      onClose={vi.fn()}
      onNotify={vi.fn()}
      onImported={vi.fn()}
      initialProducts={[]}
      {...props}
    />
  );

describe('FirstMigrationWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    api.getProducts.mockResolvedValue({ products: PRODUCTS, total: 2 });
    api.getGaps.mockResolvedValue({ gaps: {} });
  });

  it('пустой каталог: приветствие → шаг «Откуда» с выбором площадки-источника', () => {
    renderWizard();

    // Приветствие с картой шагов
    expect(screen.getByText('Перенесём ваши товары за 5 шагов')).toBeInTheDocument();
    expect(screen.getByText('Начать', { selector: 'button' })).toBeInTheDocument();

    fireEvent.click(screen.getByText('Начать', { selector: 'button' }));

    // Пустой каталог — идём на шаг загрузки источника
    expect(screen.getByText('1. Площадка-источник:')).toBeInTheDocument();
    expect(screen.getByText('2. Загрузка товаров:')).toBeInTheDocument();
    expect(screen.getByText('Ozon')).toBeInTheDocument();
    expect(screen.getByText('Wildberries')).toBeInTheDocument();
  });

  it('«Не сейчас» закрывает мастер и не помечает его пройденным', () => {
    const onClose = vi.fn();
    renderWizard({ onClose });

    fireEvent.click(screen.getByText('Не сейчас', { selector: 'button' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    // Ключ «пройден» не ставится: автопоказ возможен после перезагрузки
    expect(localStorage.getItem('first_migration_wizard_v1')).toBeNull();
  });

  it('с товарами: мастер начинает сразу с выбора площадки назначения', () => {
    renderWizard({ initialProducts: PRODUCTS });

    expect(
      screen.getByText('У вас уже есть 2 товаров — начнём сразу с выбора площадки назначения.')
    ).toBeInTheDocument();

    fireEvent.click(screen.getByText('Начать', { selector: 'button' }));

    // Шаги «Откуда»/«Товары» пропущены — сразу «Куда»
    expect(screen.getByText('Куда переносим')).toBeInTheDocument();
    expect(screen.queryByText('1. Площадка-источник:')).not.toBeInTheDocument();
  });

  it('полный цикл: площадка → перенос (SSE-прогресс) → готово → XLSX → пройден', async () => {
    api.migrateBatch.mockResolvedValue({ batch_id: 42, total: 2 });
    api.streamTaskProgress.mockImplementation(async (taskId, { onUpdate } = {}) => {
      const frame = { status: 'completed', total: 2, done: 2, success: 2, errors: 0, percent: 100 };
      onUpdate?.(frame);
      return frame;
    });
    api.exportXlsxV2.mockResolvedValue('wildberries_export.xlsx');

    renderWizard({ initialProducts: PRODUCTS });
    fireEvent.click(screen.getByText('Начать', { selector: 'button' }));

    // Запуск переноса: все товары мастера, площадка по умолчанию — wildberries
    const runBtn = screen.getByRole('button', { name: /Перенести 2 товаров на Wildberries/ });
    fireEvent.click(runBtn);

    await waitFor(() => expect(api.migrateBatch).toHaveBeenCalledWith([1, 2], 'wildberries'));
    await waitFor(() => expect(api.streamTaskProgress).toHaveBeenCalledWith(42, expect.anything()));

    // Прогресс завершился — автоматический переход к финалу мастера
    await waitFor(() => expect(screen.getByText('Перенос завершён')).toBeInTheDocument());

    // Скачивание результата
    fireEvent.click(screen.getByRole('button', { name: /Скачать файл для кабинета/ }));
    await waitFor(() => expect(api.exportXlsxV2).toHaveBeenCalledWith('wildberries', 'success'));
    await waitFor(() => expect(screen.getByText(/wildberries_export\.xlsx/)).toBeInTheDocument());

    // Завершение помечает мастера пройденным навсегда
    fireEvent.click(screen.getByText('Завершить', { selector: 'button' }));
    expect(localStorage.getItem('first_migration_wizard_v1')).toBe('true');
  });

  it('провал запуска миграции: ошибка видна, «Назад» возвращает к настройкам', async () => {
    api.migrateBatch.mockRejectedValue(new Error('Нет валидных товаров для миграции'));

    renderWizard({ initialProducts: PRODUCTS });
    fireEvent.click(screen.getByText('Начать', { selector: 'button' }));
    fireEvent.click(screen.getByRole('button', { name: /Перенести 2 товаров/ }));

    await waitFor(() =>
      expect(screen.getByText('Нет валидных товаров для миграции')).toBeInTheDocument()
    );
    // Кнопка возврата доступна — мастер не «застрял»
    const backBtn = screen.getByRole('button', { name: /Назад/ });
    fireEvent.click(backBtn);
    await waitFor(() => expect(screen.getByText('Куда переносим')).toBeInTheDocument());
  });
});
