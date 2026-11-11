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

/* ==================== 6 шагов — терминология совпадает с онбординг-туром ==================== */

const STEPS_CONTENT = [
  {
    icon: 'import',
    title: '1 · Импорт',
    desc: 'Загрузите официальную выгрузку XLSX/CSV из кабинета Ozon, Wildberries, Яндекс Маркета или Магнита — либо введите API-ключ / YML-ссылку. Импортированные товары получают статус «Ожидает».',
  },
  {
    icon: 'products',
    title: '2 · Товары и массовое редактирование',
    desc: 'Карточки — в таблице раздела «Товары»: фото, характеристики, варианты (SKU), логистика (штрихкод, габариты, НДС). Отметьте товары чекбоксами — «Обновить цену/бренд» массово меняет цену (наценка/скидка %), бренд и категорию назначения с предпросмотром «до → после» и кнопкой отмены.',
  },
  {
    icon: 'settings',
    title: '3 · Дефолты и пропуски',
    desc: 'Красный баннер показывает пропуски обязательных полей (НДС, ТН ВЭД, габариты, вес, цена, главное фото). В «Дефолтах» задайте значения один раз — глобально и по категориям — и кнопкой «Заполнить пропуски» дозаполните пустые поля у всех или только у выбранных товаров. Заполненные значения не перезаписываются.',
  },
  {
    icon: 'layers',
    title: '4 · Спецификации и шаблоны',
    desc: 'Раздел «Спецификации» загружает официальный справочник категорий площадки (обязательные поля и атрибуты) — без него миграция в новые категории будет неточной. «Шаблоны» хранят эталонные выгрузки Ozon. «Маппинг» связывает вашу категорию с категорией площадки.',
  },
  {
    icon: 'migrate',
    title: '5 · Миграция',
    desc: 'Кнопка «Мигрировать» — для одной карточки, «Мигрировать выбранные» — для пачки. Сервис сопоставляет категории, адаптирует атрибуты и формат под выбранную площадку. Товары с блокирующими пропусками (цена, главное фото) помечаются — сначала закройте пропуски.',
  },
  {
    icon: 'export',
    title: '6 · Выгрузка',
    desc: 'Кнопка «Выгрузка»: XLSX по официальному шаблону площадки (несколько файлов — ZIP). Загрузите файл в личный кабинет новой площадки — товары готовы к продаже.',
  },
];

/* ==================== Статусная модель ==================== */

const STATUSES = [
  {
    label: 'Ожидает',
    color: 'var(--accent-warning, #f59e0b)',
    desc: 'Импортирован, ждёт редактирования или миграции.',
  },
  {
    label: 'В работе',
    color: 'var(--accent-primary, #6366f1)',
    desc: 'Идёт миграция — кнопки выбора и повторной миграции недоступны.',
  },
  {
    label: 'Успешно',
    color: 'var(--accent-success, #22c55e)',
    desc: 'Перенесён на площадку — можно выгружать XLSX.',
  },
  {
    label: 'Ошибка',
    color: 'var(--danger, #ef4444)',
    desc: 'Миграция не удалась: чаще всего пропуски обязательных полей или категория не найдена в спеках. Исправьте и мигрируйте повторно.',
  },
];

/* ==================== FAQ (без тарифов — только факты о продукте) ==================== */

const FAQ = [
  {
    q: 'Нужно ли передавать API-ключи площадок?',
    a: 'Не обязательно. Доступны два способа: файл выгрузки (XLSX/CSV) или API-ключ / YML-ссылка. Ключи используются только для получения ваших товаров и не передаются третьим лицам.',
  },
  {
    q: 'Какие площадки поддерживаются?',
    a: 'Импорт: Ozon, Wildberries, Яндекс Маркет, Магнит Маркет. Миграция и выгрузка — по официальным шаблонам площадок; список растёт.',
  },
  {
    q: 'Поддерживаются ли варианты товаров (SKU)?',
    a: 'Да, варианты импортируются и экспортируются вместе с карточкой.',
  },
  {
    q: 'Что происходит с фотографиями?',
    a: 'Сервис работает со ссылками на фото из вашей выгрузки. Из карточки товара их можно скачать архивом.',
  },
  {
    q: 'Можно ли отменить массовое обновление?',
    a: 'Да. Сразу после применения под сообщением появляется кнопка «Отменить» — она восстановит прежние цену, бренд и категорию назначения. Товары, удалённые после обновления, пропускаются.',
  },
  {
    q: 'Почему миграция завершилась ошибкой?',
    a: 'Две частые причины. 1) Пропуски обязательных полей (цена, главное фото, НДС, ТН ВЭД, габариты) — закройте их кнопкой «Заполнить пропуски» из «Дефолтов». 2) Категория назначения не найдена в спецификациях площадки — загрузите спеки или выберите категорию из подсказок в массовом обновлении.',
  },
];

const HelpPage = () => (
  <div className="public-layout">
    <div style={SECTION}>
      <h1
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0.75rem',
          marginBottom: '0.5rem',
        }}
      >
        <IconWrap name="book" size={34} />
        Как это работает
      </h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem', textAlign: 'center' }}>
        Перенос товаров между маркетплейсами за 6 шагов — от файла выгрузки до готового XLSX.
      </p>

      <h2 style={{ marginBottom: '1rem' }}>6 шагов к запуску продаж на новой площадке</h2>
      {STEPS_CONTENT.map((s, i) => (
        <div key={i} style={CARD}>
          <h3
            style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <IconWrap name={s.icon} />
            {s.title}
          </h3>
          <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{s.desc}</p>
        </div>
      ))}

      <h2
        style={{
          marginTop: '2rem',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}
      >
        <IconWrap name="tag" size={22} />
        Статусы товаров
      </h2>
      {STATUSES.map((s, i) => (
        <div key={i} style={{ ...CARD, display: 'flex', gap: '0.75rem', alignItems: 'baseline' }}>
          <span
            style={{
              color: s.color,
              fontWeight: 700,
              whiteSpace: 'nowrap',
              minWidth: 90,
            }}
          >
            {s.label}
          </span>
          <span style={{ color: 'var(--text-secondary)' }}>{s.desc}</span>
        </div>
      ))}

      <h2
        style={{
          marginTop: '2rem',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}
      >
        <IconWrap name="help" size={22} color="var(--accent-warning)" />
        Частые вопросы
      </h2>
      {FAQ.map((faq, i) => (
        <div key={i} style={CARD}>
          <h4 style={{ margin: '0 0 0.5rem' }}>{faq.q}</h4>
          <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{faq.a}</p>
        </div>
      ))}

      <div
        style={{
          marginTop: '2rem',
          textAlign: 'center',
          display: 'flex',
          gap: '1rem',
          justifyContent: 'center',
          flexWrap: 'wrap',
        }}
      >
        <a
          href="#/"
          className="btn btn-primary"
          style={{ padding: '0.6rem 1.25rem', borderRadius: 6, textDecoration: 'none' }}
        >
          ← На главную
        </a>
        <button
          className="btn btn-secondary"
          onClick={() => {
            resetOnboarding();
            window.location.hash = '#/';
          }}
          style={{ padding: '0.6rem 1.25rem', borderRadius: 6 }}
        >
          <Icon name="refresh" size={16} /> Пройти тур заново
        </button>
      </div>
    </div>
  </div>
);

export default HelpPage;
