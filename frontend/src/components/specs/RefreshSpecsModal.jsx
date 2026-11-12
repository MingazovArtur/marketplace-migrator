import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import Icon from '../icons';
import { api } from '../../api';
import { PLATFORMS } from '../../utils/platformUtils';

/* =====================================================================
   Модалка обновления спеков (ЕДИНЫЙ ФОРМАТ ДЛЯ ВСЕХ ПЛОЩАДОК)
   Р3: вынесено из SpecsPage.jsx без изменения логики.
   ===================================================================== */
const RefreshSpecsModal = ({ platform, loading, message, progress, onClose, onSubmit }) => {
  const [businessId, setBusinessId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [hasServerKey, setHasServerKey] = useState(false);

  const platformInfo = PLATFORMS.find((p) => p.id === platform);
  const isOzon = platform === 'ozon';
  const isYandex = platform === 'yandex';
  const isWb = platform === 'wildberries';
  const isSupported = isOzon || isYandex || isWb;

  const isRunning = progress?.status === 'progress' || progress?.status === 'pending';

  useEffect(() => {
    if (!isOzon) {
      setHasServerKey(false);
      return;
    }
    let cancelled = false;
    api
      .getSpecKeySource(platform)
      .then((data) => {
        if (!cancelled) setHasServerKey(!!(data && data.has_server_key));
      })
      .catch(() => {
        if (!cancelled) setHasServerKey(false);
      });
    return () => {
      cancelled = true;
    };
  }, [platform, isOzon]);

  // Если пользователь вставил в одно из полей полный ключ вида "123456:uuid", автоматически разделим его на два поля
  const handleBusinessIdChange = (val) => {
    if (isOzon && val.includes(':')) {
      const [cid, keyPart] = val.split(':', 2);
      setBusinessId(cid.trim());
      if (keyPart && !apiKey) setApiKey(keyPart.trim());
      return;
    }
    setBusinessId(val);
  };

  const handleApiKeyChange = (val) => {
    if (isOzon && val.includes(':') && /^\d+\s*:/.test(val.trim())) {
      const [cid, keyPart] = val.trim().split(':', 2);
      if (!businessId) setBusinessId(cid.trim());
      setApiKey(keyPart.trim());
      return;
    }
    setApiKey(val);
  };

  const cleanId = businessId.trim();
  const cleanKey = apiKey.trim();

  const idFormatError =
    (isOzon || isYandex) && cleanId && !/^\d+$/.test(cleanId)
      ? 'ID кабинета / Client ID должен состоять только из цифр (например: 1234567).'
      : '';

  const canSubmit =
    isSupported &&
    !isRunning &&
    !idFormatError &&
    (isOzon
      ? (!!cleanId && !!cleanKey) || (!cleanId && !cleanKey && hasServerKey)
      : isYandex
        ? !!cleanId && !!cleanKey
        : isWb
          ? !!cleanKey
          : false);

  const percent =
    progress?.percent !== undefined
      ? progress.percent
      : progress?.total
        ? Math.round(((progress.done || 0) * 100) / progress.total)
        : 0;

  return (
    <div className="modal-overlay" onClick={isRunning ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">
            <Icon name="key" size={22} /> Загрузка спеков {platformInfo?.name}
          </h2>
          <button
            type="button"
            className="close-btn"
            onClick={onClose}
            title="Закрыть"
            disabled={loading && !isRunning}
          >
            <Icon name="close" size={16} />
          </button>
        </div>

        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem' }}>
          Мы подтянем структуру категорий, характеристики и словари значений через официальный API
          площадки в фоновом режиме. Ключ используется только для этого запроса.
        </p>

        {!isSupported && (
          <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
            <div>
              Для площадки «{platformInfo?.name}» используется выгрузка по эталонным XLSX-шаблонам в
              разделе «Шаблоны».
            </div>
          </div>
        )}

        {isOzon && hasServerKey && (
          <div className="alert alert-success" style={{ marginBottom: '1rem' }}>
            <div>
              <Icon name="check" size={16} style={{ marginRight: '0.5rem' }} />
              Серверный ключ Ozon настроен в .env — поля ниже можно оставить пустыми.
            </div>
          </div>
        )}

        {/* Поле 1: Номер кабинета / Client ID (единый формат) */}
        <label className="form-label">
          {isOzon
            ? '1. Номер кабинета (Client ID)'
            : isYandex
              ? '1. Номер кабинета (business_id)'
              : '1. Номер кабинета / ID продавца (необязательно для WB)'}
        </label>
        <input
          className="form-input"
          type="text"
          value={businessId}
          onChange={(e) => handleBusinessIdChange(e.target.value)}
          placeholder={
            isOzon
              ? hasServerKey
                ? 'Оставьте пустым для серверного ключа или введите Client ID (например: 1234567)'
                : 'Например: 1234567'
              : isYandex
                ? 'Например: 12345678'
                : 'Для Wildberries можно оставить пустым'
          }
          disabled={!isSupported || loading || isRunning}
        />
        <p className="form-hint" style={{ marginBottom: '0.85rem' }}>
          {isOzon ? (
            <>
              Числовой <code>Client ID</code> из личного кабинета Ozon Seller → Настройки →
              API-ключи.
            </>
          ) : isYandex ? (
            <>
              Номер бизнеса (<code>business_id</code>) из URL кабинета:{' '}
              <code>seller.market.yandex.ru/business/12345678/...</code>
            </>
          ) : (
            <>Для Wildberries авторизация выполняется по единому токену ниже.</>
          )}
        </p>

        {/* Поле 2: API-ключ / Токен (единый формат) */}
        <label className="form-label">
          {isOzon
            ? '2. API-ключ (API-Key)'
            : isYandex
              ? '2. API-ключ (ACMA:...) или OAuth-токен'
              : '2. API-ключ (токен категории «Контент»)'}
        </label>
        <input
          className="form-input"
          type="text"
          value={apiKey}
          onChange={(e) => handleApiKeyChange(e.target.value)}
          placeholder={
            isOzon
              ? hasServerKey
                ? 'Оставьте пустым для серверного ключа или введите UUID API-Key'
                : 'e30b97e3-997e-4574-8ddf-56466bcd20b8'
              : isYandex
                ? 'ACMA:... или y0_AgAAAA...'
                : 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...'
          }
          disabled={!isSupported || loading || isRunning}
        />
        <p className="form-hint">
          {isOzon ? (
            <>
              Секретный ключ <code>API-Key</code> (формат UUID) из кабинета Ozon Seller → Настройки
              → API-ключи.
            </>
          ) : isYandex ? (
            <>
              Токен выдаётся в кабинете продавца Яндекс Маркета (Настройки → Модули и API).
            </>
          ) : isWb ? (
            <>
              Ключ категории «Контент»: кабинет WB Партнёры → Настройки → Доступ к API.
            </>
          ) : (
            '—'
          )}
        </p>

        {idFormatError && (
          <div className="alert alert-error" style={{ marginTop: '0.5rem' }}>
            <div>{idFormatError}</div>
          </div>
        )}

        {/* Прогресс-бар фоновой загрузки (единый для Ozon, Яндекс Маркета и Wildberries) */}
        {isRunning && (
          <div
            style={{
              marginTop: '1rem',
              padding: '0.85rem 1rem',
              background: 'var(--bg-secondary)',
              borderRadius: 8,
              border: '1px solid var(--border-color)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '0.5rem',
                fontSize: '0.9rem',
                fontWeight: 600,
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                {progress?.total > 0
                  ? `Загрузка спецификаций ${platformInfo?.name} в фоне...`
                  : `Получаем дерево категорий ${platformInfo?.name}...`}
              </span>
              <span style={{ color: 'var(--accent-primary)', fontWeight: 700 }}>{percent}%</span>
            </div>

            <div
              style={{
                height: 8,
                background: 'var(--border-light)',
                borderRadius: 4,
                overflow: 'hidden',
                marginBottom: '0.5rem',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${percent}%`,
                  background: 'var(--accent-primary)',
                  borderRadius: 4,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>

            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Загружено:{' '}
              <strong style={{ color: 'var(--accent-success)' }}>
                {progress.success || progress.done || 0}
              </strong>{' '}
              из <strong>{progress.total || '…'}</strong>
              {progress.errors > 0 && (
                <>
                  {' '}
                  · Ошибок:{' '}
                  <strong style={{ color: 'var(--accent-danger)' }}>{progress.errors}</strong>
                </>
              )}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Вы можете закрыть это окно и продолжить работу — загрузка завершится в фоновом режиме.
            </div>
          </div>
        )}

        {progress?.status === 'completed' && (
          <div className="alert alert-success" style={{ marginTop: '0.75rem' }}>
            <div>
              ✅ Готово! Загружено <strong>{progress.success || progress.done || 0}</strong>{' '}
              категорий ({platformInfo?.name}).
              {progress.errors > 0 && (
                <>
                  {' '}
                  Ошибок: <strong>{progress.errors}</strong>.
                </>
              )}
            </div>
          </div>
        )}

        {progress?.status === 'failed' && (
          <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>
            <div>❌ {progress.error || 'Ошибка загрузки спеков'}</div>
          </div>
        )}

        {message && !progress && (
          <div
            className={`alert ${
              message.startsWith('✅')
                ? 'alert-success'
                : message.startsWith('🚀')
                  ? 'alert-info'
                  : 'alert-error'
            }`}
            style={{ marginTop: '0.75rem' }}
          >
            <div>{message}</div>
          </div>
        )}

        <div className="modal-actions">
          <Button variant="outline" onClick={onClose} disabled={loading && !isRunning}>
            {isRunning ? 'Закрыть (загрузка продолжится)' : 'Отмена'}
          </Button>
          <Button
            onClick={() => onSubmit(cleanKey, cleanId)}
            disabled={!canSubmit || loading || isRunning}
            loading={loading}
          >
            <Icon name="refresh" size={16} /> Запустить в фоне
          </Button>
        </div>
      </div>
    </div>
  );
};

export default RefreshSpecsModal;
