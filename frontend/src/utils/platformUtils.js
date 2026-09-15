/**
 * Утилиты для работы с платформами
 * Единое место для констант и функций определения платформ
 */

export const PLATFORMS = [
  { id: 'ozon', name: 'Ozon', color: '#005bff', logoText: 'O' },
  { id: 'wildberries', name: 'Wildberries', color: '#cb11ab', logoText: 'WB' },
  { id: 'yandex', name: 'Яндекс Маркет', color: '#fc3f1d', logoText: 'Я' }
];

export const PLATFORM_NAMES = {
  ozon: 'Ozon',
  wildberries: 'Wildberries',
  yandex: 'Яндекс Маркет'
};

/**
 * Определяет платформу из строки source
 * Используется и во фронтенде, и в бэкенде (platform_utils.py)
 */
export const detectPlatform = (sourceStr) => {
  if (!sourceStr) return null;
  
  const str = sourceStr.toLowerCase();
  
  // Если есть стрелка → берём последнюю часть (целевая платформа)
  if (str.includes('→')) {
    const lastPart = str.split('→').pop().trim();
    if (lastPart.includes('ozon')) return 'ozon';
    if (lastPart.includes('wildberries') || lastPart.includes('wb')) return 'wildberries';
    if (lastPart.includes('яндекс') || lastPart.includes('yandex')) return 'yandex';
  }
  
  // Иначе ищем во всей строке
  if (str.includes('ozon')) return 'ozon';
  if (str.includes('wildberries') || str.includes('wb')) return 'wildberries';
  if (str.includes('яндекс') || str.includes('yandex')) return 'yandex';
  
  return null;
};

/**
 * Получает доступные платформы для миграции (исключая текущую)
 */
export const getAvailablePlatforms = (currentSource, allPlatforms = PLATFORMS) => {
  const currentPlatform = detectPlatform(currentSource);
  return allPlatforms.filter(p => p.id !== currentPlatform);
};

/**
 * Получает платформы, недоступные для выбранных товаров
 */
export const getUnavailablePlatforms = (products, selectedIds, allPlatforms = PLATFORMS) => {
  const selectedProducts = products.filter(p => selectedIds.includes(p.id));
  const sourcePlatforms = new Set();
  
  selectedProducts.forEach(product => {
    const platform = detectPlatform(product.source);
    if (platform) sourcePlatforms.add(platform);
  });
  
  return allPlatforms.filter(p => sourcePlatforms.has(p.id));
};