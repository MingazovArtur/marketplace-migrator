import React from 'react';
import Button from '../common/Button';

const FEATURES = [
  { icon: '📥', title: 'Импорт из файлов', text: 'XLSX/CSV из кабинетов Ozon, WB, Яндекс Маркета и Магнит Маркета — с предпросмотром и валидацией.' },
  { icon: '🔄', title: 'Миграция карточек', text: 'Перенос товаров между площадками с автомаппингом категорий и пересчётом цен.' },
  { icon: '📤', title: 'Экспорт под формат ЛК', text: 'Готовые файлы для загрузки в кабинет площадки + проверка карточек перед выгрузкой.' },
  { icon: '📜', title: 'История операций', text: 'Полный журнал импортов, миграций и экспортов — в профиле и во вкладке «История».' },
];

const Landing = ({ onOpenAuth }) => (
  <div className="landing">
    <section className="landing-hero">
      <h1>Универсальный перенос карточек товаров</h1>
      <p>Импортируйте товары из одного маркетплейса и выгружайте в другой — без ручного копирования.</p>
      <div className="landing-cta">
        <Button onClick={() => onOpenAuth('register')}>Создать аккаунт</Button>
        <Button variant="secondary" onClick={() => onOpenAuth('login')}>Войти</Button>
      </div>
    </section>

    <section className="landing-features">
      {FEATURES.map((f) => (
        <div key={f.title} className="card landing-card">
          <div className="landing-card-icon">{f.icon}</div>
          <h3>{f.title}</h3>
          <p>{f.text}</p>
        </div>
      ))}
    </section>
  </div>
);

export default Landing;