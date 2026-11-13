/**
 * Хранилище состояния онбординг-тура.
 * STORAGE_KEY версионируется: смена ключа показывает обновлённый тур
 * всем, кто прошёл предыдущую версию. Отдельный модуль, а не экспорт из
 * OnboardingTour.jsx: файл компонента должен экспортировать только
 * компонент (react-refresh/only-export-components); resetOnboarding
 * используется страницей «Справка».
 */

export const STORAGE_KEY = 'onboarding_tour_v2';

/**
 * Сброс онбординга: показывает тур заново.
 * Диспатчит событие — тур перезапускается, даже если уже смонтирован.
 */
export const resetOnboarding = () => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event('onboarding-restart'));
};
