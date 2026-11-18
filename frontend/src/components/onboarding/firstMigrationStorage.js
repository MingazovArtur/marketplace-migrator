/**
 * Хранилище состояния мастера первой миграции.
 *
 * Отдельный модуль (не экспорт из FirstMigrationWizard.jsx) — по той же
 * причине, что и onboardingStorage.js: файл компонента должен экспортировать
 * только компонент (react-refresh/only-export-components).
 *
 * Два уровня состояния:
 *  - WIZARD_KEY (localStorage)   — мастер ПРОЙДЕН до конца: автопоказ больше
 *                                  никогда не беспокоит пользователя;
 *  - DISMISS_KEY (sessionStorage) — мастер закрыли на середине («Не сейчас»,
 *                                  крестик): до конца сессии браузера
 *                                  автопоказ не повторяется, но после
 *                                  перезагрузки страницы мастер предложит
 *                                  себя ещё раз.
 *
 * Ручной запуск (кнопка в «Товарах» / «Справке») не смотрит на эти ключи —
 * мастером можно пользоваться сколько угодно раз.
 */

export const WIZARD_STORAGE_KEY = 'first_migration_wizard_v1';
const DISMISS_KEY = 'first_migration_wizard_dismissed';

/** Мастер полностью пройден (автопоказ отключён навсегда). */
export const isWizardCompleted = () => {
  try {
    return !!localStorage.getItem(WIZARD_STORAGE_KEY);
  } catch {
    return false;
  }
};

/** Отметить мастер пройденным. */
export const completeWizard = () => {
  try {
    localStorage.setItem(WIZARD_STORAGE_KEY, 'true');
  } catch {
    /* приватный режим — просто продолжаем */
  }
};

/** Мастер закрыли до завершения (не беспокоить до конца сессии). */
export const dismissWizardForSession = () => {
  try {
    sessionStorage.setItem(DISMISS_KEY, 'true');
  } catch {
    /* ignore */
  }
};

/** Был ли dismiss в этой сессии. */
export const isWizardDismissedThisSession = () => {
  try {
    return !!sessionStorage.getItem(DISMISS_KEY);
  } catch {
    return false;
  }
};

/**
 * Ручной перезапуск: кнопка «Мастер первой миграции» (Справка). Диспатчит
 * событие — App открывает мастера, даже если тот уже смонтирован. Ключи
 * не трогаем: ручной запуск не зависит от статуса автопоказа.
 */
export const restartWizard = () => {
  window.dispatchEvent(new Event('wizard:restart'));
};
