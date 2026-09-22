import React from 'react';
import Icon from '../components/icons';
import { resetOnboarding } from '../components/onboarding/OnboardingTour';

const SECTION = { maxWidth: 800, margin: '0 auto', padding: '2rem 1.5rem' };
const CARD = {
  padding: '1.5rem',
  marginBottom: '1rem',
  background: 'var(--bg-secondary)',
  border: '1px solid var(--border-color)',
  borderRadius: 12,
};

const IconWrap = ({ name, size = 20, color = 'var(--accent-primary)' }) => (
  <span style={{ color, display: 'inline-flex', flexShrink: 0 }}>
    <Icon name={name} size={size} />
  </span>
);

const STEPS_CONTENT = [
  { icon: 'import', title: '1. Импорт', desc: 'Загрузите выгрузку XLSX/CSV из кабинета Ozon, WB, Яндекс Маркет или Магнит. Либо введите API-ключ или YML-ссылку.' },
  { icon: 'edit', title: '2. Редактирование', desc: 'Исправьте цены, описания, добавьте характеристики. Массовое редактирование для больших каталогов.' },
  { icon: 'migrate', title: '3. Миграция', desc: 'Выберите товары и целевую площадку. Сервис мапит категории и адаптирует формат.' },
  { icon: 'export', title: '4. Выгрузка', desc: 'Скачайте XLSX, готовый к загрузке в личный кабинет новой площадки.' },
];

const FAQ = [
  {
    q: 'Нужно ли передавать API-ключи площадок?',
    a: 'Не обязательно. Доступны два способа: файл выгрузки (XLSX/CSV) или API-ключ / YML-ссылка. Ключи используются только для получения ваших товаров и не передаются третьим лицам.',
  },
  { q: 'Сколько стоит сервис?', a: 'Первые 50 SKU — бесплатно. Дальше — тарифы Pro и Business.' },
  { q: 'Поддерживаются ли варианты товаров (SKU)?', a: 'Да, варианты импортируются и экспортируются вместе с карточкой.' },
  { q: 'Что делать с фото?', a: 'Сервис копирует ссылки на фото. Можно скачать их в архив через кнопку в карточке.' },
];

const HelpPage = () => (
  <div className="public-layout">
    <div style={SECTION}>
      <h1 style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
        <IconWrap name="book" size={34} />
        Как это работает
      </h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem', textAlign: 'center' }}>
        Быстрый гайд по переносу товаров между маркетплейсами.
      </p>

      <h2 style={{ marginBottom: '1rem' }}>4 шага к запуску продаж на новой площадке</h2>
      {STEPS_CONTENT.map((s, i) => (
        <div key={i} style={CARD}>
          <h3 style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <IconWrap name={s.icon} />
            {s.title}
          </h3>
          <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{s.desc}</p>
        </div>
      ))}

      <h2 style={{ marginTop: '2rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <IconWrap name="help" size={22} color="var(--accent-warning)" />
        Частые вопросы
      </h2>
      {FAQ.map((faq, i) => (
        <div key={i} style={CARD}>
          <h4 style={{ margin: '0 0 0.5rem' }}>{faq.q}</h4>
          <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{faq.a}</p>
        </div>
      ))}

      <div style={{ marginTop: '2rem', textAlign: 'center', display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
        <a href="#/" className="btn btn-primary" style={{ padding: '0.6rem 1.25rem', borderRadius: 6, textDecoration: 'none' }}>
          ← На главную
        </a>
        <button
          className="btn btn-secondary"
          onClick={() => { resetOnboarding(); window.location.hash = '#/'; }}
          style={{ padding: '0.6rem 1.25rem', borderRadius: 6 }}
        >
          <Icon name="refresh" size={16} /> Пройти тур заново
        </button>
      </div>
    </div>
  </div>
);

export default HelpPage;