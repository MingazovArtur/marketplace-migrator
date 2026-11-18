import React, { useState, useEffect, useCallback } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import { api } from '../api';
import { PLATFORMS } from '../utils/platformUtils';

/* Админ-панель: пользователи, статистика сервиса, журнал доступа.
 * Маршрут /admin доступен только роли admin (проверка и в App.jsx,
 * и на бэкенде get_current_admin_user — роль читается из БД каждый
 * запрос, понижение применяется мгновенно). */

const PAGE_SIZE = 25;

const platformName = (id) => PLATFORMS.find((p) => p.id === id)?.name || id || '—';

/* Бэкенд отдаёт naive-UTC isoformat — дописываем Z, чтобы Date не
 * интерпретировал его как локальное время сервера браузера. */
const fmtDate = (iso) => {
  if (!iso) return '—';
  const normalized = /[Z+]/.test(iso) ? iso : `${iso}Z`;
  return new Date(normalized).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const ACTION_LABELS = {
  register: 'регистрация',
  login_success: 'вход',
  login_failed: 'неудачный вход',
  logout: 'выход',
  demo_login: 'демо-вход',
  admin_update_user: 'изменение админом',
};

const RoleBadge = ({ role }) =>
  role === 'admin' ? (
    <span className="badge badge-success">админ</span>
  ) : (
    <span className="badge badge-pending">user</span>
  );

const AdminPage = ({ user, onNotify }) => {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [logs, setLogs] = useState([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [updatingId, setUpdatingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [statsData, usersData, logsData] = await Promise.all([
        api.getAdminStats(),
        api.getAdminUsers(search.trim(), page * PAGE_SIZE, PAGE_SIZE),
        api.getAccessLogs(50),
      ]);
      setStats(statsData);
      setUsers(usersData.users || []);
      setUsersTotal(usersData.total || 0);
      setLogs(logsData.logs || []);
    } catch (e) {
      setError(e.message || 'Не удалось загрузить данные');
    } finally {
      setLoading(false);
    }
  }, [search, page]);

  useEffect(() => {
    load();
  }, [load]);

  const applyUserUpdate = async (target, payload, okMessage) => {
    setUpdatingId(target.id);
    setError('');
    try {
      const data = await api.updateAdminUser(target.id, payload);
      setUsers((prev) => prev.map((u) => (u.id === data.user.id ? data.user : u)));
      if (onNotify) onNotify(okMessage);
    } catch (e) {
      setError(e.message || 'Не удалось обновить пользователя');
    } finally {
      setUpdatingId(null);
    }
  };

  if (user && user.role !== 'admin') {
    return (
      <div className="card">
        <div className="alert alert-error">Доступ только для администраторов</div>
      </div>
    );
  }

  const pages = Math.max(1, Math.ceil(usersTotal / PAGE_SIZE));

  return (
    <div>
      <header className="header">
        <div>
          <h1 className="header-title">Админ-панель</h1>
          <p className="header-subtitle">
            Пользователи, роли и активность сервиса — без ручных SQL-запросов
          </p>
        </div>
        <div className="header-actions">
          <Button variant="outline" onClick={load} disabled={loading} loading={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
        </div>
      </header>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
          <div>{error}</div>
        </div>
      )}

      {loading && !stats ? (
        <div className="card">
          <div className="loading-spinner">
            <div className="spinner" />
            <p style={{ color: 'var(--text-secondary)' }}>Загрузка...</p>
          </div>
        </div>
      ) : (
        <>
          {/* ==== Сводка по сервису ==== */}
          {stats && (
            <div className="stats-grid" style={{ marginBottom: '1rem' }}>
              <div className="stat-card">
                <div className="stat-value">{stats.users_total}</div>
                <div className="stat-label">Пользователей</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  +{stats.new_users_7d} за неделю
                </div>
              </div>
              <div className="stat-card success">
                <div className="stat-value">{stats.active_users_7d}</div>
                <div className="stat-label">Входили за 7 дней</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{stats.products_total}</div>
                <div className="stat-label">Товаров</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{stats.migrations_total}</div>
                <div className="stat-label">Миграций всего</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{stats.operations_7d}</div>
                <div className="stat-label">Операций за 7 дней</div>
                {stats.platforms_7d?.length > 0 && (
                  <div
                    style={{
                      fontSize: '0.8rem',
                      color: 'var(--text-muted)',
                      marginTop: '0.25rem',
                    }}
                  >
                    {stats.platforms_7d
                      .slice(0, 3)
                      .map((p) => `${platformName(p.platform)}: ${p.count}`)
                      .join(' · ')}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ==== Пользователи ==== */}
          <div className="card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
            <div
              style={{
                display: 'flex',
                gap: '0.75rem',
                alignItems: 'center',
                flexWrap: 'wrap',
                marginBottom: '1rem',
              }}
            >
              <h2 style={{ fontSize: '1.05rem', margin: 0 }}>Пользователи</h2>
              <input
                className="form-input"
                style={{ maxWidth: '280px' }}
                placeholder="Поиск по логину или email…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
              />
              <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                {usersTotal > 0
                  ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, usersTotal)} из ${usersTotal}`
                  : 'никого не найдено'}
              </span>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem' }}>
                <Button
                  className="btn-sm"
                  variant="outline"
                  disabled={page === 0 || loading}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  ← Назад
                </Button>
                <Button
                  className="btn-sm"
                  variant="outline"
                  disabled={page >= pages - 1 || loading}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Вперёд →
                </Button>
              </div>
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Логин</th>
                    <th>Email</th>
                    <th>Роль</th>
                    <th>Статус</th>
                    <th>Товаров</th>
                    <th>Последний вход</th>
                    <th>Регистрация</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const self = u.id === user?.id;
                    const busy = updatingId === u.id;
                    return (
                      <tr key={u.id}>
                        <td>{u.id}</td>
                        <td>
                          {u.username}
                          {self && (
                            <span
                              style={{
                                color: 'var(--text-muted)',
                                fontSize: '0.8rem',
                                marginLeft: '0.4rem',
                              }}
                            >
                              (вы)
                            </span>
                          )}
                        </td>
                        <td style={{ color: 'var(--text-secondary)' }}>{u.email}</td>
                        <td>
                          <RoleBadge role={u.role} />
                        </td>
                        <td>
                          {u.is_active ? (
                            <span className="ok-text">активен</span>
                          ) : (
                            <span className="err-text">отключён</span>
                          )}
                        </td>
                        <td>{u.products_count ?? '—'}</td>
                        <td>{fmtDate(u.last_login_at)}</td>
                        <td>{fmtDate(u.created_at)}</td>
                        <td>
                          <div
                            className="row-actions"
                            style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}
                          >
                            <Button
                              className="btn-sm"
                              variant="outline"
                              disabled={busy || self}
                              loading={busy}
                              onClick={() =>
                                applyUserUpdate(
                                  u,
                                  { role: u.role === 'admin' ? 'user' : 'admin' },
                                  u.role === 'admin'
                                    ? `Права администратора сняты у ${u.username}`
                                    : `${u.username} назначен администратором`
                                )
                              }
                            >
                              {u.role === 'admin' ? 'Снять админа' : 'Сделать админом'}
                            </Button>
                            <Button
                              className="btn-sm"
                              variant="outline"
                              disabled={busy || self}
                              loading={busy}
                              onClick={() =>
                                applyUserUpdate(
                                  u,
                                  { is_active: !u.is_active },
                                  u.is_active
                                    ? `${u.username} отключён (сессии завершаются сразу)`
                                    : `${u.username} снова активен`
                                )
                              }
                            >
                              {u.is_active ? 'Отключить' : 'Включить'}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {users.length === 0 && !loading && (
                    <tr>
                      <td colSpan={9} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                        Никого не найдено
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ==== Журнал доступа ==== */}
          <div className="card" style={{ padding: '1.25rem' }}>
            <h2 style={{ fontSize: '1.05rem', margin: '0 0 1rem' }}>
              Журнал доступа (последние {logs.length})
            </h2>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Время</th>
                    <th>Пользователь</th>
                    <th>Действие</th>
                    <th>IP</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td>{fmtDate(log.created_at)}</td>
                      <td>{log.username || `id:${log.user_id ?? '—'}`}</td>
                      <td>{ACTION_LABELS[log.action] || log.action}</td>
                      <td style={{ color: 'var(--text-secondary)' }}>{log.ip || '—'}</td>
                    </tr>
                  ))}
                  {logs.length === 0 && (
                    <tr>
                      <td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                        Журнал пуст
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default AdminPage;
