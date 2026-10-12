import React from 'react';
import Button from '../common/Button';
import Icon from '../icons';

const FEATURES = [
  {
    icon: 'import',
    title: 'Импорт из файлов',
    text: 'XLSX/CSV из кабинетов Ozon, WB, Яндекс Маркета и Магнит Маркета — с предпросмотром и валидацией.',
  },
  {
    icon: 'migrate',
    title: 'Миграция карточек',
    text: 'Перенос товаров между площадками с автомаппингом категорий и пересчётом цен.',
  },
  {
    icon: 'export',
    title: 'Экспорт под формат ЛК',
    text: 'Готовые файлы для загрузки в кабинет площадки + проверка карточек перед выгрузкой.',
  },
  {
    icon: 'history',
    title: 'История операций',
    text: 'Полный журнал импортов, миграций и экспортов — в профиле и во вкладке «История».',
  },
];

const HOW_IT_WORKS = [
  {
    step: 1,
    icon: 'import',
    title: 'Импортируйте',
    text: 'Загрузите выгрузку из кабинета маркетплейса или введите API-ключ.',
  },
  {
    step: 2,
    icon: 'edit',
    title: 'Отредактируйте',
    text: 'Проверьте цены, описания, характеристики. Массовое редактирование для больших каталогов.',
  },
  {
    step: 3,
    icon: 'migrate',
    title: 'Перенесите',
    text: 'Выберите товары и целевую площадку — сервис адаптирует формат и категории.',
  },
  {
    step: 4,
    icon: 'export',
    title: 'Выгрузите',
    text: 'Скачайте готовый XLSX и загрузите в личный кабинет новой площадки.',
  },
];

const Landing = ({ onOpenAuth }) => (
  <div className="landing">
    <section className="landing-hero">
      <h1>Универсальный перенос карточек товаров</h1>
      <p>
        Импортируйте товары из одного маркетплейса и выгружайте в другой — без ручного копирования.
      </p>
      <div className="landing-cta">
        <Button onClick={() => onOpenAuth('register')}>Создать аккаунт</Button>
        <Button variant="secondary" onClick={() => onOpenAuth('login')}>
          Войти
        </Button>
      </div>
    </section>

    <section className="landing-features">
      {FEATURES.map((f) => (
        <div key={f.title} className="card landing-card">
          <div className="landing-card-icon">
            <Icon name={f.icon} size={40} />
          </div>
          <h3>{f.title}</h3>
          <p>{f.text}</p>
        </div>
      ))}
    </section>

    {/* ✅ Новая секция: Как это работает */}
    <section
      style={{
        maxWidth: '1000px',
        margin: '4rem auto 0',
        padding: '0 1.5rem',
      }}
    >
      <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.8rem', marginBottom: '0.5rem' }}>Как это работает</h2>
        <p style={{ color: 'var(--text-secondary)' }}>
          4 шага от выгрузки до запуска продаж на новой площадке
        </p>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
        }}
      >
        {HOW_IT_WORKS.map((item) => (
          <div
            key={item.step}
            className="card"
            style={{ padding: '1.5rem', textAlign: 'center', position: 'relative' }}
          >
            <div
              style={{
                position: 'absolute',
                top: '-0.75rem',
                left: '50%',
                transform: 'translateX(-50%)',
                background: 'var(--accent-primary)',
                color: 'white',
                width: '1.75rem',
                height: '1.75rem',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 600,
                fontSize: '0.9rem',
              }}
            >
              {item.step}
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                color: 'var(--accent-primary)',
                marginBottom: '0.75rem',
                marginTop: '0.5rem',
              }}
            >
              <Icon name={item.icon} size={40} />
            </div>
            <h3 style={{ marginBottom: '0.5rem' }}>{item.title}</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: 0 }}>
              {item.text}
            </p>
          </div>
        ))}
      </div>
      <div style={{ textAlign: 'center', marginTop: '2rem' }}>
        <a
          href="#/help"
          style={{
            color: 'var(--accent-primary)',
            textDecoration: 'none',
            fontSize: '0.95rem',
          }}
        >
          Подробнее в справке →
        </a>
      </div>
    </section>

    {/* ✅ Юридический футер + ссылка на помощь */}
    <footer
      style={{
        marginTop: '3rem',
        paddingTop: '1.5rem',
        borderTop: '1px solid var(--border)',
        display: 'flex',
        justifyContent: 'center',
        gap: '1.5rem',
        fontSize: '0.85rem',
        flexWrap: 'wrap',
      }}
    >
      <a
        href="#/help"
        style={{
          color: 'var(--text-muted)',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.3rem',
        }}
      >
        <Icon name="book" size={16} />
        Как это работает
      </a>
      <a href="#/privacy" style={{ color: 'var(--text-muted)' }}>
        Политика конфиденциальности
      </a>
      <a href="#/terms" style={{ color: 'var(--text-muted)' }}>
        Пользовательское соглашение
      </a>
    </footer>
  </div>
);

export default Landing;
