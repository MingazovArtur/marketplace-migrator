import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import Icon from '../icons';
import { STORAGE_KEY } from './onboardingStorage';

/**
 * Онбординг-тур по рабочему интерфейсу (7 карточек: приветствие + 6 шагов).
 *
 * Шаги привязаны к реальным элементам через data-onboarding-атрибуты
 * (см. App.jsx / Sidebar.jsx / ProductsPage.jsx — таблица товаров рендерится
 * прямо в ProductsPage).
 * Если элемент не нашёлся (нет товаров, пользователь не на странице «Товары») —
 * карточка показывается по центру с пояснением, а не ломает тур.
 *
 * Клавиатура: Esc — пропустить, ← — назад, → / Enter — далее.
 * Клик по затемнению ничего не сбрасывает (защита от случайного клика).
 *
 * STORAGE_KEY версионируется: смена ключа показывает обновлённый тур
 * всем, кто прошёл предыдущую версию.
 */

// Сколько раз ищем цель (200 мс × 15 ≈ 3 с) прежде чем показать карточку по центру
const TARGET_RETRIES = 15;
const TARGET_RETRY_MS = 200;

const STEPS = [
  {
    target: '[data-onboarding="welcome"]',
    icon: 'logo',
    title: 'Добро пожаловать!',
    description:
      'Перенесём ваши товары между маркетплейсами — от файла выгрузки до готового XLSX. 6 коротких шагов. Тур можно пропустить — всё то же самое есть на странице «Справка».',
    position: 'center',
  },
  {
    target: '[data-onboarding="import-btn"]',
    icon: 'import',
    title: 'Шаг 1 · Импорт',
    description:
      'Загрузите выгрузку XLSX/CSV из кабинета Ozon, Wildberries, Яндекс Маркета или Магнита — либо введите API-ключ / YML-ссылку.',
    position: 'bottom',
    fallback: 'Кнопка «Импорт» — в шапке раздела «Товары».',
  },
  {
    target: '[data-onboarding="products-table"]',
    icon: 'products',
    title: 'Шаг 2 · Товары',
    description:
      'После импорта карточки появятся в таблице. Редактируйте фото, характеристики, варианты и логистику; чекбоксами выбирайте товары для массовых действий.',
    position: 'top',
    fallback: 'Таблица товаров появится здесь после первого импорта.',
  },
  {
    target: '[data-onboarding="defaults-btn"]',
    icon: 'settings',
    title: 'Шаг 3 · Дефолты и пропуски',
    description:
      'Кнопка «Дефолты»: задайте НДС, ТН ВЭД, габариты и вес один раз — и дозаполняйте пропуски обязательных полей у всех товаров в один клик.',
    position: 'bottom',
    fallback: 'Кнопка «Дефолты» — на панели фильтров раздела «Товары».',
  },
  {
    target: '[data-onboarding="specs-nav"]',
    icon: 'layers',
    title: 'Шаг 4 · Спеки и шаблоны',
    description:
      'В разделе «Спецификации» загрузите справочник категорий площадки — миграция будет точнее. «Шаблоны» — эталонные выгрузки Ozon.',
    position: 'right',
    fallback: 'Разделы «Спецификации» и «Шаблоны» — в меню слева.',
  },
  {
    target: '[data-onboarding="migrate-btn"]',
    icon: 'migrate',
    title: 'Шаг 5 · Миграция',
    description:
      'Кнопка «Мигрировать»: выберите площадку назначения — сервис сопоставит категории и адаптирует карточки под формат её личного кабинета.',
    position: 'top',
    fallback: 'Кнопка «Мигрировать» появится в строке каждого товара после импорта.',
  },
  {
    target: '[data-onboarding="export-btn"]',
    icon: 'export',
    title: 'Шаг 6 · Выгрузка',
    description:
      'Скачайте готовый XLSX (или ZIP) и загрузите файл в кабинет новой площадки. Готово — товары продаются!',
    position: 'bottom',
    fallback: 'Кнопка «Выгрузка» — в шапке раздела «Товары».',
  },
];

const isCompleted = () => {
  try {
    return !!localStorage.getItem(STORAGE_KEY);
  } catch (e) {
    return false;
  }
};

const OnboardingTour = () => {
  const [active, setActive] = useState(() => !isCompleted());
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState(null);
  const [targetMissing, setTargetMissing] = useState(false);
  const tooltipRef = useRef(null);
  const [tipSize, setTipSize] = useState({ w: 380, h: 220 });

  const currentStep = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const finish = () => {
    try {
      localStorage.setItem(STORAGE_KEY, 'true');
    } catch (e) {
      /* приватный режим — просто закрываем */
    }
    setActive(false);
    window.dispatchEvent(new Event('onboarding-complete'));
  };

  const next = () => (isLast ? finish() : setStep(step + 1));
  const prev = () => setStep(Math.max(0, step - 1));

  /* Перезапуск тура: страница «Справка» → «Пройти тур заново» */
  useEffect(() => {
    const onRestart = () => {
      setStep(0);
      setActive(true);
    };
    window.addEventListener('onboarding-restart', onRestart);
    return () => window.removeEventListener('onboarding-restart', onRestart);
  }, []);

  /* Поиск цели шага с ограниченным числом попыток (без вечного ретрая) */
  useEffect(() => {
    if (!active) return undefined;

    let retries = 0;
    let timer = null;

    const updateRect = () => {
      const el = document.querySelector(currentStep.target);
      if (el) {
        const r = el.getBoundingClientRect();
        setRect({
          top: r.top - 6,
          left: r.left - 6,
          width: r.width + 12,
          height: r.height + 12,
        });
        setTargetMissing(false);
        // Подтягиваем цель в видимую область (например, кнопки в шапке при скролле)
        const vr = el.getBoundingClientRect();
        if (vr.top < 0 || vr.bottom > window.innerHeight) {
          el.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
        return;
      }
      setRect(null);
      setTargetMissing(true);
      if (retries < TARGET_RETRIES) {
        retries += 1;
        timer = setTimeout(updateRect, TARGET_RETRY_MS);
      }
    };

    updateRect();
    window.addEventListener('resize', updateRect);
    window.addEventListener('scroll', updateRect, true);
    return () => {
      if (timer) clearTimeout(timer);
      window.removeEventListener('resize', updateRect);
      window.removeEventListener('scroll', updateRect, true);
    };
  }, [active, step, currentStep.target]);

  /* Клавиатура: Esc — пропустить, ← — назад, → / Enter — далее */
  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        finish();
      } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        e.preventDefault();
        next();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        prev();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  /* Реальный размер тултипа — для аккуратного позиционирования */
  useLayoutEffect(() => {
    if (!active || !tooltipRef.current) return;
    const r = tooltipRef.current.getBoundingClientRect();
    if (r.width && r.height) setTipSize({ w: r.width, h: r.height });
  }, [active, step, rect]);

  if (!active) return null;

  /* Позиционирование: предпочитенная сторона, при нехватке места — разворот */
  let tooltipStyle = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' };
  if (rect && currentStep.position !== 'center') {
    const margin = 20;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const { w, h } = tipSize;

    const fits = (left, top) => left >= 8 && top >= 8 && left + w <= vw - 8 && top + h <= vh - 8;

    const candidates = {
      bottom: [rect.left + rect.width / 2 - w / 2, rect.top + rect.height + margin],
      top: [rect.left + rect.width / 2 - w / 2, rect.top - margin - h],
      right: [rect.left + rect.width + margin, rect.top + rect.height / 2 - h / 2],
      left: [rect.left - margin - w, rect.top + rect.height / 2 - h / 2],
    };
    const flip = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };

    let [left, top] = candidates[currentStep.position] || candidates.bottom;
    if (!fits(left, top)) {
      [left, top] = candidates[flip[currentStep.position]] || candidates.top;
    }
    left = Math.max(8, Math.min(vw - w - 8, left));
    top = Math.max(8, Math.min(vh - h - 8, top));

    tooltipStyle = { top, left, transform: 'none' };
  }

  return (
    <>
      <div className="onboarding-overlay" />
      {rect && <div className="onboarding-spotlight" style={rect} />}
      <div
        className="onboarding-tooltip"
        style={tooltipStyle}
        role="dialog"
        aria-modal="true"
        aria-label={`Тур: ${currentStep.title}`}
        ref={tooltipRef}
        tabIndex={-1}
      >
        <div className="onboarding-step-indicator">
          {step === 0 ? 'Начало' : `Шаг ${step} из ${STEPS.length - 1}`}
        </div>
        <h3>
          <span style={{ color: 'var(--accent-primary)', display: 'inline-flex' }}>
            <Icon name={currentStep.icon} size={20} />
          </span>
          {currentStep.title}
        </h3>
        <p>{currentStep.description}</p>
        {targetMissing && currentStep.fallback && (
          <p className="onboarding-fallback">{currentStep.fallback}</p>
        )}
        <div className="onboarding-dots">
          {STEPS.map((s, i) => (
            <button
              key={s.title}
              type="button"
              className={`onboarding-dot ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`}
              onClick={() => setStep(i)}
              title={s.title}
            />
          ))}
        </div>
        <div className="onboarding-actions">
          <button className="onboarding-skip" onClick={finish} title="Esc">
            Пропустить
          </button>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {step > 0 && (
              <button className="onboarding-btn-secondary" onClick={prev} title="←">
                Назад
              </button>
            )}
            <button className="onboarding-btn" onClick={next} autoFocus>
              {isLast ? 'Начать работу' : 'Далее →'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default OnboardingTour;
