import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';
import App from './App';

/* Smoke-тест App: связка «роутер + кэш + layout». Мокаем агрегатор api —
 * из сетевых вызовов при маунте нужны только getMe/getStats/getProducts/
 * getGaps/getSpecNames/getEditHistory, остальные сработают по кликам. */
vi.mock('./api', () => ({
  API_URL: '/api',
  api: {
    getMe: vi.fn(),
    getStats: vi.fn(),
    getProducts: vi.fn(),
    getGaps: vi.fn(),
    getSpecNames: vi.fn(),
    getEditHistory: vi.fn(),
  },
}));

import { api } from './api';

const USER = { id: 7, email: 'user@example.com', role: 'user' };
const STATS = { total: 1, pending: 1, success: 0, error: 0, processing: 0 };
const LIST = {
  products: [{ id: 1, title: 'Тестовый товар', status: 'pending', price: 100, photos: [] }],
  total: 1,
};

const renderApp = (initialEntry = '/') => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe('App (smoke: маршруты + TanStack Query)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    // Тур обучения не запускаем — он накрывает интерфейс оверлеем
    localStorage.setItem('onboarding_tour_v2', 'true');
    api.getMe.mockResolvedValue(USER);
    api.getStats.mockResolvedValue(STATS);
    api.getProducts.mockResolvedValue(LIST);
    api.getGaps.mockResolvedValue({ gaps: {} });
    api.getSpecNames.mockResolvedValue([]);
    api.getEditHistory.mockResolvedValue({ has_undo: false });
  });

  it('гость видит публичный лендинг, рабочие маршруты не рендерятся', async () => {
    api.getMe.mockRejectedValue(new Error('Не авторизован (HTTP 401)'));
    renderApp();

    await waitFor(() => expect(api.getMe).toHaveBeenCalled());
    await waitFor(() => {
      expect(document.querySelector('.public-layout')).toBeInTheDocument();
    });
    // Список товаров не грузится — рабочий layout не смонтирован
    expect(api.getProducts).not.toHaveBeenCalled();
    expect(document.querySelector('.app-layout')).not.toBeInTheDocument();
  });

  it('залогиненный: «/» редиректит в последнюю вкладку (по умолчанию /products)', async () => {
    renderApp('/');

    // Дефолтный вид — «Товары»: страница запросила список
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Товары' })).toBeInTheDocument());
    expect(api.getProducts).toHaveBeenCalled();
    expect(screen.getByRole('link', { name: /Дашборд/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Товары/ })).toBeInTheDocument();
  });

  it('навигация по сайдбару переключает маршруты без перезагрузки', async () => {
    renderApp('/');

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Товары' })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('link', { name: /Дашборд/ }));
    await waitFor(() =>
      expect(screen.getByText('Обзор миграции товаров')).toBeInTheDocument()
    );
    expect(screen.getByRole('heading', { name: 'Дашборд' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: /Импорт/ }));
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Импорт товаров' })).toBeInTheDocument()
    );
  });

  it('админский маршрут /specs-monitor обычному пользователю недоступен', async () => {
    renderApp('/specs-monitor');

    // Не админ → тихий редирект на «Товары»
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Товары' })).toBeInTheDocument());
  });
});
