import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import React from 'react';
import AdminPage from './AdminPage';

/* Регрессионный тест контракта api: AdminPage зовёт методы с префиксом
 * Admin (getAdminStats/getAdminUsers/updateAdminUser) — в агрегаторе
 * api/index.js непрефиксованный getStats затирается statsApi (статистика
 * селлера, GET /stats), поэтому имена админ-методов обязаны быть
 * однозначными. Мок повторяет РЕАЛЬНЫЙ состав api/admin.js: если страница
 * позовёт метод, которого нет, — TypeError и тест падает. */
vi.mock('../api', () => ({
  api: {
    getAdminStats: vi.fn(),
    getAdminUsers: vi.fn(),
    getAccessLogs: vi.fn(),
    updateAdminUser: vi.fn(),
  },
}));

import { api } from '../api';

const STATS = {
  success: true,
  users_total: 5,
  new_users_7d: 2,
  active_users_7d: 3,
  products_total: 120,
  migrations_total: 40,
  operations_7d: 17,
  platforms_7d: [{ platform: 'ozon', count: 9 }, { platform: 'wildberries', count: 8 }],
};

const USERS = {
  success: true,
  total: 1,
  users: [
    {
      id: 7,
      username: 'seller1',
      email: 'seller1@example.com',
      role: 'user',
      is_active: true,
      email_verified: true,
      created_at: '2026-11-01T10:00:00',
      products_count: 12,
      last_login_at: '2026-11-17T09:00:00',
    },
  ],
};

const renderPage = (props = {}) =>
  render(<AdminPage user={{ id: 1, role: 'admin', username: 'admin' }} onNotify={vi.fn()} {...props} />);

describe('AdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAdminStats.mockResolvedValue(STATS);
    api.getAdminUsers.mockResolvedValue(USERS);
    api.getAccessLogs.mockResolvedValue({ success: true, logs: [] });
    api.updateAdminUser.mockResolvedValue({
      success: true,
      changed: ['role=admin'],
      user: { ...USERS.users[0], role: 'admin' },
    });
  });

  it('загружает сводку, пользователей и журнал — методы api существуют', async () => {
    renderPage();

    await waitFor(() => expect(api.getAdminStats).toHaveBeenCalledTimes(1));
    expect(api.getAdminUsers).toHaveBeenCalledWith('', 0, 25);
    expect(api.getAccessLogs).toHaveBeenCalledWith(50);

    // Сводка и строка пользователя отрисованы — страница жива, нет «not a function»
    expect(screen.getByText('Пользователей')).toBeInTheDocument();
    expect(screen.getByText('seller1')).toBeInTheDocument();
  });

  it('смена роли: PATCH уходит админ-методом, строка обновляется на месте', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('seller1')).toBeInTheDocument());

    // Кнопка смены роли в строке пользователя (role=user → «Сделать админом»)
    const promoteBtn = await screen.findByRole('button', { name: 'Сделать админом' });
    fireEvent.click(promoteBtn);

    await waitFor(() =>
      expect(api.updateAdminUser).toHaveBeenCalledWith(7, { role: 'admin' })
    );
    // Строка перерисовалась из ответа сервера — бейдж админа на месте
    await waitFor(() => expect(screen.getByText('админ', { selector: '.badge' })).toBeInTheDocument());
  });
});
