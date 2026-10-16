import React, { useState, useEffect, useCallback, useRef } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import { api } from '../api';

const PLATFORM_OPTIONS = [
  { id: 'yandex', name: 'Яндекс Маркет', color: '#fc3f1d', badge: 'ЯМ' },
  { id: 'ozon', name: 'Ozon', color: '#005bff', badge: 'Ozon' },
  { id: 'wildberries', name: 'Wildberries', color: '#cb11ab', badge: 'WB' },
  { id: 'magnit', name: 'Магнит Маркет', color: '#e31235', badge: 'ММ' },
];

const PLATFORM_INSTRUCTIONS = {
  yandex: [
    'В кабинете Яндекс Маркета откройте «Товары → Каталог → Загрузить товары».',
    'Нажмите кнопку «Скачать шаблон» (шаг 1 в окне загрузки файла).',
    'Выберите площадку «Яндекс Маркет» ниже и загрузите скачанный .xlsx файл.',
    'Поле категории можно оставить «Универсальный (все категории)» — при выгрузке система сама удалит строку-пример («Дрель Makita») и подставит ваши товары в оригинальные столбцы.',
  ],
  ozon: [
    'В кабинете Ozon: «Товары и цены» → «Загрузить товары по XLSX» → шаг 1 «Выберите категорию и тип».',
    'Выберите категорию (например, «Одежда > Аксессуары > Панама») и скачайте шаблон.',
    'Укажите категорию в формате «Родитель / Тип» (или оставьте «Универсальный», если используете один базовый шаблон).',
    'Загрузите файл ниже — он станет общим эталоном для всех пользователей системы.',
  ],
  wildberries: [
    'В кабинете WB Партнёры перейдите в «Товары → Карточки товаров → Добавить → Много товаров».',
    'Выберите нужную категорию (предмет) и скачайте шаблон Excel.',
    'Загрузите полученный .xlsx файл ниже, выбрав площадку «Wildberries».',
  ],
  magnit: [
    'В кабинете Магнит Маркет перейдите в раздел управления ассортиментом и скачайте XLSX-шаблон.',
    'Загрузите файл ниже, выбрав площадку «Магнит Маркет».',
  ],
};

const UNIVERSAL_LABEL = 'Универсальный (все категории)';

const formatDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
};

const TemplatesPage = ({ onNotify }) => {
  const [selectedPlatform, setSelectedPlatform] = useState('yandex');
  const [filterPlatform, setFilterPlatform] = useState('all');
  const [categoryName, setCategoryName] = useState(UNIVERSAL_LABEL);
  const [file, setFile] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [specNames, setSpecNames] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const notify = useCallback(
    (msg) => {
      if (onNotify) onNotify(msg);
    },
    [onNotify]
  );

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listOzonTemplatesMeta();
      setTemplates(data?.templates || []);
    } catch (e) {
      notify('❌ ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  const loadSpecNames = useCallback(async (pl) => {
    try {
      const names = await api.getSpecNames(pl);
      setSpecNames(Array.isArray(names) ? names : []);
    } catch {
      setSpecNames([]);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  useEffect(() => {
    loadSpecNames(selectedPlatform);
    if (selectedPlatform === 'yandex') {
      setCategoryName(UNIVERSAL_LABEL);
    }
  }, [selectedPlatform, loadSpecNames]);

  const handleFileChange = (e) => {
    const picked = e.target.files?.[0] || null;
    setFile(picked);
    if (!picked) return;

    // Если имя файла вида ozon_Родитель_Тип.xlsx — подсказываем категорию автоматически
    const base = picked.name.replace(/\.xlsx$/i, '');
    const m = base.match(/^(ozon|yandex|wb|wildberries|magnit)[_-](.+)$/i);
    if (m && m[2]) {
      const parts = m[2].split('_').filter(Boolean);
      if (parts.length >= 2 && selectedPlatform === 'ozon') {
        setCategoryName(`${parts[0]} / ${parts.slice(1).join(' ')}`);
      }
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) {
      notify('❌ Выберите файл шаблона (.xlsx)');
      return;
    }
    const finalCat = (categoryName || '').trim() || UNIVERSAL_LABEL;
    setUploading(true);
    try {
      const res = await api.uploadOzonTemplate(finalCat, file, selectedPlatform);
      notify(`✅ ${res.message || 'Эталонный шаблон сохранён'}`);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await loadTemplates();
    } catch (err) {
      notify('❌ ' + err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (tpl) => {
    try {
      await api.downloadOzonTemplate(tpl.category_name, tpl.platform || 'ozon');
    } catch (e) {
      notify('❌ ' + e.message);
    }
  };

  const handleDelete = async (tpl) => {
    try {
      await api.deleteOzonTemplate(tpl.category_name, tpl.platform || 'ozon');
      notify(`✅ Эталон «${tpl.category_name}» (${tpl.platform || 'ozon'}) удалён`);
      await loadTemplates();
    } catch (e) {
      notify('❌ ' + e.message);
    }
  };

  const visibleTemplates =
    filterPlatform === 'all'
      ? templates
      : templates.filter((t) => (t.platform || 'ozon') === filterPlatform);

  const currentPlatformMeta =
    PLATFORM_OPTIONS.find((p) => p.id === selectedPlatform) || PLATFORM_OPTIONS[0];

  return (
    <div className="view-content">
      <header className="header">
        <div>
          <h1 className="header-title">Шаблоны площадок</h1>
          <p className="header-subtitle">
            Эталонные XLSX-шаблоны Яндекс Маркета, Ozon, Wildberries и Магнит Маркета: выгрузка 1:1 с кабинетом площадки
          </p>
        </div>
        <div className="header-actions">
          <Button variant="secondary" onClick={loadTemplates} disabled={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
        </div>
      </header>

      {/* 1. Выбор площадки */}
      <div className="card" style={{ marginBottom: '1.25rem' }}>
        <h3 style={{ marginBottom: '0.75rem', fontSize: '1.05rem' }}>
          1. Выберите площадку, с которой скачан шаблон
        </h3>
        <div className="platform-selector" style={{ margin: '0.5rem 0 1rem' }}>
          {PLATFORM_OPTIONS.map((p) => {
            const countForPlatform = templates.filter(
              (t) => (t.platform || 'ozon') === p.id
            ).length;
            return (
              <button
                key={p.id}
                type="button"
                className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`}
                onClick={() => setSelectedPlatform(p.id)}
              >
                <div
                  className="platform-logo"
                  style={{
                    backgroundColor: selectedPlatform === p.id ? p.color : 'var(--bg-tertiary)',
                    color: selectedPlatform === p.id ? '#fff' : 'var(--text-muted)',
                    fontSize: '1rem',
                  }}
                >
                  {p.badge}
                </div>
                <span>{p.name}</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {countForPlatform > 0 ? `Загружено: ${countForPlatform}` : 'Нет шаблонов'}
                </span>
              </button>
            );
          })}
        </div>

        {/* Инструкция под выбранную площадку */}
        <div
          style={{
            background: 'var(--bg-glass)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)',
            padding: '1rem 1.25rem',
          }}
        >
          <h4 style={{ marginBottom: '0.5rem' }}>
            Как получить эталонный шаблон ({currentPlatformMeta.name})
          </h4>
          <ol
            style={{
              paddingLeft: '1.25rem',
              color: 'var(--text-secondary)',
              fontSize: '0.9rem',
              lineHeight: 1.6,
            }}
          >
            {(PLATFORM_INSTRUCTIONS[selectedPlatform] || PLATFORM_INSTRUCTIONS.ozon).map(
              (step, idx) => (
                <li key={idx}>{step}</li>
              )
            )}
          </ol>
        </div>
      </div>

      {/* 2. Форма загрузки эталонного шаблона */}
      <form className="card" onSubmit={handleUpload} style={{ marginBottom: '1.5rem' }}>
        <h3
          style={{
            marginBottom: '0.75rem',
            fontSize: '1.05rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Icon name="template" size={18} /> 2. Загрузить эталонный шаблон для{' '}
          <span style={{ color: currentPlatformMeta.color }}>{currentPlatformMeta.name}</span>
        </h3>

        <div
          style={{
            display: 'flex',
            gap: '0.75rem',
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ flex: '1 1 280px' }}>
            <input
              className="form-input"
              type="text"
              list={`tpl-spec-names-${selectedPlatform}`}
              value={categoryName}
              onChange={(e) => setCategoryName(e.target.value)}
              placeholder={
                selectedPlatform === 'yandex'
                  ? 'Универсальный (все категории)'
                  : 'Универсальный (все категории) или Одежда / Футболка'
              }
            />
            <datalist id={`tpl-spec-names-${selectedPlatform}`}>
              <option value={UNIVERSAL_LABEL} />
              {specNames.map((n) => (
                <option key={n} value={n} />
              ))}
            </datalist>
          </div>

          {categoryName !== UNIVERSAL_LABEL && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setCategoryName(UNIVERSAL_LABEL)}
              title="Использовать этот шаблон как единый для всех категорий площадки"
            >
              Сделать универсальным
            </Button>
          )}

          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx"
              onChange={handleFileChange}
              style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}
            />
          </div>

          <Button type="submit" disabled={uploading || !file} loading={uploading}>
            <Icon name="import" size={16} /> Сохранить эталон
          </Button>
        </div>

        <p className="form-hint" style={{ marginTop: '0.6rem', marginBottom: 0 }}>
          💡 Если указано <strong>«{UNIVERSAL_LABEL}»</strong> (или если это единственный загруженный
          шаблон для площадки), система будет автоматически использовать его при выгрузке любых
          товаров на <strong>{currentPlatformMeta.name}</strong>: удалит пример из шаблона и запишет
          ваши товары в оригинальные столбцы.
        </p>
      </form>

      {/* 3. Список загруженных эталонов */}
      <div className="card">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '0.75rem',
            marginBottom: '1rem',
          }}
        >
          <h3 style={{ margin: 0, fontSize: '1.05rem' }}>
            Загруженные эталонные шаблоны ({visibleTemplates.length})
          </h3>

          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            <Button
              variant={filterPlatform === 'all' ? 'primary' : 'secondary'}
              onClick={() => setFilterPlatform('all')}
            >
              Все ({templates.length})
            </Button>
            {PLATFORM_OPTIONS.map((p) => {
              const cnt = templates.filter((t) => (t.platform || 'ozon') === p.id).length;
              return (
                <Button
                  key={p.id}
                  variant={filterPlatform === p.id ? 'primary' : 'secondary'}
                  onClick={() => setFilterPlatform(p.id)}
                >
                  {p.name} ({cnt})
                </Button>
              );
            })}
          </div>
        </div>

        {visibleTemplates.length === 0 ? (
          <div className="empty-state" style={{ padding: '2rem 1rem' }}>
            <p className="empty-state-text">
              Эталонные шаблоны пока не загружены. Скачайте шаблон в кабинете площадки и загрузите
              его в форме выше.
            </p>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="stats-table">
              <thead>
                <tr>
                  <th>Площадка</th>
                  <th>Назначение / Категория</th>
                  <th>Файл</th>
                  <th>Столбцов</th>
                  <th>Кто загрузил</th>
                  <th>Дата загрузки</th>
                  <th style={{ textAlign: 'right' }}>Действия</th>
                </tr>
              </thead>
              <tbody>
                {visibleTemplates.map((t) => {
                  const pl = t.platform || 'ozon';
                  const pMeta =
                    PLATFORM_OPTIONS.find((p) => p.id === pl) || PLATFORM_OPTIONS[1];
                  return (
                    <tr key={`${pl}::${t.category_name}`}>
                      <td>
                        <span
                          className="source-badge"
                          style={{
                            borderColor: pMeta.color,
                            color: pMeta.color,
                            fontWeight: 700,
                          }}
                        >
                          {pMeta.name}
                        </span>
                      </td>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {t.category_name}
                      </td>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}>{t.file}</td>
                      <td>{t.columns ?? '—'}</td>
                      <td>{t.uploaded_by || '—'}</td>
                      <td>{formatDate(t.uploaded_at)}</td>
                      <td style={{ textAlign: 'right' }}>
                        <div className="row-actions">
                          <Button
                            variant="secondary"
                            onClick={() => handleDownload(t)}
                            title="Скачать исходный эталонный файл"
                          >
                            <Icon name="import" size={14} /> Скачать
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => handleDelete(t)}
                            title="Удалить эталон"
                            style={{ color: 'var(--accent-danger)' }}
                          >
                            <Icon name="trash" size={14} />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default TemplatesPage;