import React, { useState, useEffect, useCallback } from 'react';
import Button from '../components/common/Button';
import Icon from '../components/icons';
import EmptyState from '../components/common/EmptyState';
import { api } from '../api';

/**
 * ✅ Автоподстановка категории из имени файла эталона:
 *   ozon_Одежда_Футболка.xlsx       → «Одежда / Футболка»
 *   ozon_Белье_Комплект_трусов.xlsx → «Белье / Комплект трусов»
 */
const suggestCategoryFromFilename = (filename) => {
  const m = (filename || '').match(/^ozon_(.+)\.xlsx$/i);
  if (!m) return null;
  const parts = m[1].split('_').map((p) => p.trim()).filter(Boolean);
  if (parts.length >= 2) return `${parts[0]} / ${parts.slice(1).join(' ')}`;
  return parts[0] ? parts[0].replace(/_/g, ' ').trim() : null;
};

const fmtDate = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '—' : d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
};

/**
 * Страница «Шаблоны площадок»: управление ЭТАЛОННЫМИ XLSX-шаблонами Ozon.
 * Шаблоны ОБЩИЕ для всех пользователей: загрузил один — пользуются все.
 * Выгрузка автоматически собирает файл на эталоне категории товара.
 */
const TemplatesPage = ({ onNotify }) => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [specNames, setSpecNames] = useState([]);

  const [category, setCategory] = useState('');
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [busyCat, setBusyCat] = useState(null);

  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const d = await api.listOzonTemplatesMeta();
      setTemplates(d.templates || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    api.getSpecNames('ozon').then(setSpecNames).catch(() => setSpecNames([]));
  }, [load]);

  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(''), 6000);
    return () => clearTimeout(t);
  }, [message]);

  const handleUpload = async () => {
    if (!category.trim() || !file) return;
    setUploading(true);
    setError('');
    setMessage('');
    try {
      const r = await api.uploadOzonTemplate(category.trim(), file);
      setMessage(`✅ ${r.message || 'Эталон сохранён.'}`);
      setFile(null);
      setCategory('');
      await load();
      onNotify?.('✅ Эталонный шаблон сохранён');
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (cat) => {
    setBusyCat(cat);
    try {
      await api.downloadOzonTemplate(cat);
      setMessage(`📥 Эталон «${cat}» скачан.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyCat(null);
    }
  };

  const handleDelete = async (cat) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Удалить эталонный шаблон для категории «${cat}»?\nВыгрузка вернётся к генерации из спека.`)) return;
    setBusyCat(cat);
    try {
      await api.deleteOzonTemplate(cat);
      setMessage(`🗑 Эталон «${cat}» удалён.`);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyCat(null);
    }
  };

  return (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">Шаблоны площадок</h1>
          <p className="header-subtitle">
            Эталонные XLSX-шаблоны Ozon: формат выгрузки 1:1 с кабинетом площадки
          </p>
        </div>
        <div className="header-actions">
          <Button variant="secondary" onClick={load} disabled={loading}>
            <Icon name="refresh" size={16} /> Обновить
          </Button>
        </div>
      </header>

      {/* ==================== Инструкция ==================== */}
      <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
        <h4 style={{ margin: '0 0 0.5rem' }}>Как получить эталонный шаблон</h4>
        <ol style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <li>В кабинете Ozon: «Товары и цены» → «Загрузить товары по XLSX» → шаг 1 «Выберите категорию и тип».</li>
          <li>Выберите категорию (например, «Одежда &gt; Аксессуары &gt; Панама») и скачайте шаблон.</li>
          <li>
            Переименуйте файл в <code>ozon_Родитель_Тип.xlsx</code> (необязательно, но категория подставится сама):
            {' '}<code>ozon_Аксессуары_Панама.xlsx</code>.
          </li>
          <li>Загрузите файл ниже — он станет общим для всех пользователей системы.</li>
        </ol>
        <p className="form-hint" style={{ marginTop: '0.5rem', marginBottom: 0 }}>
          💡 В кабинете путь категории трёхуровневый («Одежда &gt; Аксессуары &gt; Панама»), а в системе —
          двухуровневый («Аксессуары / Панама»). Вводите в любом формате: имя нормализуется и сверяется со спеками.
        </p>
      </div>

      {/* ==================== Загрузка нового эталона ==================== */}
      <div className="card" style={{ padding: '0.9rem 1rem', marginBottom: '0.75rem' }}>
        <h4 style={{ margin: '0 0 0.6rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Icon name="template" size={16} /> Загрузить эталонный шаблон
        </h4>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            className="form-input"
            list="tpl-page-categories"
            placeholder="Одежда / Футболка"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ flex: 1, minWidth: 260 }}
          />
          <datalist id="tpl-page-categories">
            {specNames.map((n) => (<option key={n} value={n} />))}
          </datalist>
          <input
            type="file"
            accept=".xlsx"
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              setFile(f);
              if (f && !category.trim()) {
                const suggested = suggestCategoryFromFilename(f.name);
                if (suggested) setCategory(suggested);
              }
            }}
          />
          <Button onClick={handleUpload} disabled={!category.trim() || !file || uploading} loading={uploading}>
            <Icon name="import" size={16} /> Сохранить эталон
          </Button>
        </div>
        {file && (
          <p className="form-hint" style={{ marginTop: '0.4rem', marginBottom: 0 }}>
            Файл: <strong>{file.name}</strong> → категория: <strong>{category || '—'}</strong>
          </p>
        )}
      </div>

      {error && <div className="alert alert-error"><div>{error}</div></div>}
      {message && <div className="alert alert-success"><div>{message}</div></div>}

      {/* ==================== Список эталонов ==================== */}
      {loading && !templates.length ? (
        <div className="card">
          <div className="loading-spinner">
            <div className="spinner" />
            <p style={{ color: 'var(--text-secondary)' }}>Загрузка списка эталонов...</p>
          </div>
        </div>
      ) : !templates.length ? (
        <EmptyState
          icon={<Icon name="template" size={56} />}
          title="Эталонных шаблонов пока нет"
          description="Загрузите XLSX-шаблон из кабинета Ozon — выгрузка будет собираться на его основе и приниматься площадкой без ошибок."
        />
      ) : (
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead style={{ background: 'var(--bg-secondary)' }}>
              <tr>
                <th style={{ textAlign: 'left', padding: '0.6rem' }}>Категория</th>
                <th style={{ textAlign: 'center', padding: '0.6rem' }}>Колонок</th>
                <th style={{ textAlign: 'left', padding: '0.6rem' }}>Загружен</th>
                <th style={{ textAlign: 'left', padding: '0.6rem' }}>Кто загрузил</th>
                <th style={{ textAlign: 'center', padding: '0.6rem' }}>Действия</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => (
                <tr key={t.category_name} style={{ borderBottom: '1px solid var(--border-light)' }}>
                  <td style={{ padding: '0.6rem', fontWeight: 600 }}>
                    ✅ {t.category_name}
                  </td>
                  <td style={{ padding: '0.6rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    {t.columns ?? '—'}
                  </td>
                  <td style={{ padding: '0.6rem', color: 'var(--text-secondary)' }}>
                    {fmtDate(t.uploaded_at)}
                  </td>
                  <td style={{ padding: '0.6rem', color: 'var(--text-secondary)' }}>
                    {t.uploaded_by || '—'}
                  </td>
                  <td style={{ padding: '0.6rem' }}>
                    <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'center' }}>
                      <Button
                        variant="secondary" size="small"
                        title="Скачать текущий эталон"
                        disabled={busyCat === t.category_name}
                        onClick={() => handleDownload(t.category_name)}
                      >
                        <Icon name="template" size={15} />
                      </Button>
                      <Button
                        variant="secondary" size="small"
                        title="Удалить эталон"
                        disabled={busyCat === t.category_name}
                        onClick={() => handleDelete(t.category_name)}
                        style={{ color: 'var(--danger, #ef4444)' }}
                      >
                        <Icon name="trash" size={15} />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="form-hint" style={{ marginTop: '0.75rem' }}>
        ℹ️ Шаблоны общие: их видят и используют все пользователи системы. При выгрузке файл товара
        собирается на эталоне его категории (mapped_category); если эталона нет — используется генерация из спека.
      </p>
    </>
  );
};

export default TemplatesPage;