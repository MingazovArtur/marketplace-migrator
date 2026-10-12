export const PLATFORMS = [
  { id: 'ozon', name: 'Ozon', color: '#005bff', logoText: 'O', importMethods: ['key', 'file'] },
  {
    id: 'wildberries',
    name: 'Wildberries',
    color: '#cb11ab',
    logoText: 'WB',
    importMethods: ['key', 'file'],
  },
  {
    id: 'yandex',
    name: 'Яндекс Маркет',
    color: '#fc3f1d',
    logoText: 'Я',
    importMethods: ['key', 'file'],
  },
  {
    id: 'magnit',
    name: 'Магнит Маркет',
    color: '#e31235',
    logoText: 'ММ',
    importMethods: ['file'],
  }, // ✅ только файл
];

export const PLATFORM_NAMES = {
  ozon: 'Ozon',
  wildberries: 'Wildberries',
  yandex: 'Яндекс Маркет',
  magnit: 'Магнит Маркет',
};

export const detectPlatform = (sourceStr) => {
  if (!sourceStr) return null;
  const str = sourceStr.toLowerCase();
  if (str.includes('→')) {
    const lastPart = str.split('→').pop().trim();
    if (lastPart.includes('ozon')) return 'ozon';
    if (lastPart.includes('wildberries') || lastPart.includes('wb')) return 'wildberries';
    if (lastPart.includes('яндекс') || lastPart.includes('yandex')) return 'yandex';
    if (lastPart.includes('магнит') || lastPart.includes('magnit') || lastPart.includes('kazan'))
      return 'magnit';
  }
  if (str.includes('ozon')) return 'ozon';
  if (str.includes('wildberries') || str.includes('wb')) return 'wildberries';
  if (str.includes('яндекс') || str.includes('yandex')) return 'yandex';
  if (str.includes('магнит') || str.includes('magnit') || str.includes('kazan')) return 'magnit';
  return null;
};

export const getAvailablePlatforms = (currentSource, allPlatforms = PLATFORMS) => {
  const currentPlatform = detectPlatform(currentSource);
  return allPlatforms.filter((p) => p.id !== currentPlatform);
};

export const getUnavailablePlatforms = (products, selectedIds, allPlatforms = PLATFORMS) => {
  const selectedProducts = products.filter((p) => selectedIds.includes(p.id));
  const sourcePlatforms = new Set();
  selectedProducts.forEach((product) => {
    const platform = detectPlatform(product.source);
    if (platform) sourcePlatforms.add(platform);
  });
  return allPlatforms.filter((p) => sourcePlatforms.has(p.id));
};
