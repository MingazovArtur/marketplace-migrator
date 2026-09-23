import React, { useEffect, useState } from 'react';
import Icon from '../icons';
import { api } from '../../api';

const MISSING_LABELS = {
  barcode: 'штрихкод (EAN)',
  dimensions: 'габариты упаковки',
  vat: 'ставка НДС',
};

/* ✅ Сворачиваемый чек-лист требований площадки (из официальной документации Ozon) */
export const ExportRequirementsChecklist = ({ platform = 'ozon' }) => {
  const [open, setOpen] = useState(false);

  const rules = [
    'Скачайте актуальный XLS-шаблон в личном кабинете площадки перед каждой загрузкой — шаблоны регулярно обновляются.',
    'Не меняйте структуру файла: листы, столбцы, типы ячеек. Заполните все листы (в т.ч. «Документация PDF», «Озон.Видео»).',
    'Красные поля обязательны. Числа — без единиц измерения: 606, а не «606 г».',
    'Несколько значений — через точку с запятой без пробелов: «белый;голубой;зелёный».',
    'Регистр характеристик важен: «белый» и «Белый» — разные товары (риск дублей).',
    'Штрихкод (EAN) обязателен для всех схем продаж; габариты упаковки — вес г и Ш/В/Д мм.',
    'НДС: «Не облагается» (УСН), 10% или 22%. Код ОКПД/ТН ВЭД — для маркируемых категорий.',
  ];

  return (
    <div className="export-safety">
      <button type="button" className="export-safety-toggle" onClick={() => setOpen(!open)}>
        <Icon name="warning" size={16} />
        Требования {platform} к XLS-шаблону
        <span style={{ marginLeft: 'auto' }}>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <>
          <ul className="export-safety-list">
            {rules.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          <p className="export-safety-links">
            <a href="https://seller-edu.ozon.ru/libra/work-with-goods/zagruzka-tovarov/creating-goods/cherez-xls-shablon" target="_blank" rel="noopener noreferrer">
              Документация Ozon
            </a>
            {' · '}
            <a href="https://seller.ozon.ru/app/products/create" target="_blank" rel="noopener noreferrer">
              Скачать шаблон в ЛК
            </a>
          </p>
        </>
      )}
    </div>
  );
};

/* ✅ Сводка валидации: чего не хватает товарам перед экспортом */
export const ExportValidationSummary = ({ platform }) => {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.validateExport(platform)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [platform]);

  if (!data) return null;
  if (data.total === 0) return null;

  // Все товары валидны
  if (data.errors === 0 && data.warnings === 0) {
    return (
      <div className="export-safety-ok">
        <Icon name="check" size={16} />
        Все {data.total} товаров готовы к экспорту — прошли валидацию по спекам {platform}.
      </div>
    );
  }

  const hasErrors = data.errors > 0;
  const borderColor = hasErrors ? 'rgba(239, 68, 68, 0.4)' : 'rgba(245, 158, 11, 0.4)';
  const bgColor = hasErrors ? 'rgba(239, 68, 68, 0.08)' : 'rgba(245, 158, 11, 0.08)';
  const textColor = hasErrors ? 'var(--accent-danger)' : 'var(--accent-warning)';

  return (
    <div className="export-safety-warn" style={{ borderColor, background: bgColor }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, color: textColor }}>
        <Icon name="warning" size={16} />
        {hasErrors
          ? `${data.errors} ошибок, ${data.warnings} предупреждений`
          : `${data.warnings} предупреждений`}
        {hasErrors && ' — экспорт может быть отклонён площадкой'}
      </div>

      {/* Кнопка раскрытия деталей */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        style={{
          marginTop: '0.5rem',
          padding: '0.25rem 0.5rem',
          background: 'transparent',
          border: '1px solid currentColor',
          borderRadius: '4px',
          color: 'inherit',
          cursor: 'pointer',
          fontSize: '0.8rem',
        }}
      >
        {expanded ? 'Скрыть детали ▲' : `Показать ${data.issues.length} проблемных товаров ▼`}
      </button>

      {/* Детальный список проблем */}
      {expanded && (
        <div style={{ marginTop: '0.75rem' }}>
          {data.issues.slice(0, 10).map((item) => (
            <div
              key={item.product_id}
              style={{
                marginBottom: '0.5rem',
                padding: '0.5rem',
                background: 'var(--bg-secondary)',
                borderRadius: '4px',
                fontSize: '0.85rem',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
                #{item.product_id} {item.product_name}
                <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                  ({item.category})
                </span>
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
                {item.issues.map((issue, idx) => (
                  <li key={idx} style={{ color: issue.severity === 'error' ? 'var(--accent-danger)' : 'var(--accent-warning)' }}>
                    {issue.severity === 'error' ? '❌' : '⚠️'} {issue.message}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {data.issues.length > 10 && (
            <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              …и ещё {data.issues.length - 10} товаров с проблемами
            </p>
          )}
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem' }}>
            💡 Исправьте проблемы через кнопку «Логистика» (📦) в таблице товаров или в модалках редактирования атрибутов.
          </p>
        </div>
      )}
    </div>
  );
};