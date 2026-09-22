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

  useEffect(() => {
    let cancelled = false;
    api.validateExport(platform)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [platform]);

  if (!data) return null;

  if (data.total === 0) return null;

  if (data.issues_count === 0) {
    return (
      <div className="export-safety-ok">
        <Icon name="export" size={16} />
        Все {data.total} товаров готовы к экспорту: штрихкоды, габариты и НДС заполнены.
      </div>
    );
  }

  return (
    <div className="export-safety-warn">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
        <Icon name="warning" size={16} />
        {data.issues_count} из {data.total} товаров не готовы к экспорту
      </div>
      <ul className="export-safety-list">
        {data.issues.slice(0, 5).map((iss) => (
          <li key={iss.id}>
            {iss.name} — не хватает: {iss.missing.map((m) => MISSING_LABELS[m] || m).join(', ')}
          </li>
        ))}
        {data.issues_count > 5 && <li>…и ещё {data.issues_count - 5}</li>}
      </ul>
      <p style={{ margin: '0.4rem 0 0', fontSize: '0.8rem' }}>
        Заполните данные кнопкой «коробка» в таблице товаров — иначе площадка отклонит файл.
      </p>
    </div>
  );
};