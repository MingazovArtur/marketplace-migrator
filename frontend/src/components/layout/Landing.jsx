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

const Landing = ({ onOpenAuth }) => (
  <div className="landing">
    <section className="landing-hero">
      <h1>Универсальный перенос карточек товаров</h1>
      <p>
        Импортируйте товары из одного маркетплейса и выгружайте в другой — без ручного копирования.
      </p>
      <div className="landing-cta">
        <Button onClick={() => onOpenAuth('register')}>Создать аккаунт</Button>
        <Button variant="secondary" onClick={() => onOpenAuth('login')}>Войти</Button>
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

    {/* ✅ Юридический футер */}
    <footer style={{
      marginTop: '3rem',
      paddingTop: '1.5rem',
      borderTop: '1px solid var(--border)',
      display: 'flex',
      justifyContent: 'center',
      gap: '1.5rem',
      fontSize: '0.85rem',
      flexWrap: 'wrap',
    }}>
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