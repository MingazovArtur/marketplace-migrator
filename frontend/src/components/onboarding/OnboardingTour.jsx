import React, { useEffect, useState } from 'react';
import Icon from '../icons';

const STEPS = [
  {
    target: '[data-onboarding="welcome"]',
    icon: 'logo',
    title: 'Добро пожаловать!',
    description:
      'Давайте перенесём ваши товары между маркетплейсами. Это займёт 4 шага. Тур можно пропустить.',
    position: 'center',
  },
  {
    target: '[data-onboarding="import-btn"]',
    icon: 'import',
    title: 'Шаг 1: Импорт',
    description: 'Загрузите выгрузку из Ozon, WB, Яндекс Маркет или Магнит. Либо введите API-ключ.',
    position: 'right',
  },
  {
    target: '[data-onboarding="products-table"]',
    icon: 'products',
    title: 'Шаг 2: Товары',
    description:
      'Здесь появятся ваши карточки. Можно редактировать цены, описания, характеристики.',
    position: 'top',
  },
  {
    target: '[data-onboarding="migrate-btn"]',
    icon: 'migrate',
    title: 'Шаг 3: Миграция',
    description:
      'Выберите товары и площадку назначения — сервис подготовит карточки под формат ЛК.',
    position: 'bottom',
  },
  {
    target: '[data-onboarding="export-btn"]',
    icon: 'export',
    title: 'Шаг 4: Выгрузка',
    description: 'Скачайте готовый XLSX и загрузите в личный кабинет площадки. Готово!',
    position: 'left',
  },
];

const STORAGE_KEY = 'onboarding_completed';

const OnboardingTour = () => {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState(null);

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return;

    const updateRect = () => {
      const target = STEPS[step]?.target;
      if (!target || STEPS[step].position === 'center') {
        setRect(null);
        return;
      }
      const el = document.querySelector(target);
      if (!el) {
        // Если элемент ещё не отрендерен — повтор через 200мс
        setTimeout(updateRect, 200);
        return;
      }
      const r = el.getBoundingClientRect();
      setRect({
        top: r.top - 6,
        left: r.left - 6,
        width: r.width + 12,
        height: r.height + 12,
      });
    };

    updateRect();
    window.addEventListener('resize', updateRect);
    window.addEventListener('scroll', updateRect);
    return () => {
      window.removeEventListener('resize', updateRect);
      window.removeEventListener('scroll', updateRect);
    };
  }, [step]);

  if (localStorage.getItem(STORAGE_KEY)) return null;

  const currentStep = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const finish = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    window.dispatchEvent(new Event('onboarding-complete'));
  };

  const next = () => (isLast ? finish() : setStep(step + 1));
  const prev = () => setStep(Math.max(0, step - 1));

  // Позиция тултипа
  let tooltipStyle = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' };
  if (rect && currentStep.position !== 'center') {
    const margin = 20;
    const positions = {
      top: { top: rect.top - margin - 200, left: rect.left + rect.width / 2 - 190 },
      bottom: { top: rect.top + rect.height + margin, left: rect.left + rect.width / 2 - 190 },
      left: { top: rect.top + rect.height / 2 - 80, left: rect.left - 400 },
      right: { top: rect.top + rect.height / 2 - 80, left: rect.left + rect.width + margin },
    };
    tooltipStyle = { ...positions[currentStep.position], transform: 'none' };
    tooltipStyle.top = Math.max(20, Math.min(window.innerHeight - 280, tooltipStyle.top));
    tooltipStyle.left = Math.max(20, Math.min(window.innerWidth - 400, tooltipStyle.left));
  }

  return (
    <>
      <div className="onboarding-overlay" onClick={finish} />
      {rect && <div className="onboarding-spotlight" style={rect} />}
      <div className="onboarding-tooltip" style={tooltipStyle}>
        <div className="onboarding-step-indicator">
          Шаг {step + 1} из {STEPS.length}
        </div>
        <h3>
          <span style={{ color: 'var(--accent-primary)', display: 'inline-flex' }}>
            <Icon name={currentStep.icon} size={20} />
          </span>
          {currentStep.title}
        </h3>
        <p>{currentStep.description}</p>
        <div className="onboarding-actions">
          <button className="onboarding-skip" onClick={finish}>
            Пропустить
          </button>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {step > 0 && (
              <button className="onboarding-btn-secondary" onClick={prev}>
                Назад
              </button>
            )}
            <button className="onboarding-btn" onClick={next}>
              {isLast ? 'Начать работу' : 'Далее →'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default OnboardingTour;

// Хелпер для сброса онбординга (для отладки)
export const resetOnboarding = () => localStorage.removeItem(STORAGE_KEY);
