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
  },
  {
    id: 'megamarket',
    name: 'Мегамаркет',
    color: '#8b3ffd',
    logoText: 'СММ',
    importMethods: ['key', 'file'],
  },
  {
    id: 'holodilnik',
    name: 'Холодильник.ру',
    color: '#0072bc',
    logoText: 'ХЛ',
    importMethods: ['key', 'file'],
  },
  {
    id: 'aliexpress',
    name: 'AliExpress',
    color: '#ff4747',
    logoText: 'AE',
    importMethods: ['key', 'file'],
  },
];

export const PLATFORM_NAMES = {
  ozon: 'Ozon',
  wildberries: 'Wildberries',
  yandex: 'Яндекс Маркет',
  magnit: 'Магнит Маркет',
  megamarket: 'Мегамаркет',
  holodilnik: 'Холодильник.ру',
  aliexpress: 'AliExpress',
};

const matchPlatformToken = (s) => {
  if (s.includes('ozon') || s.includes('озон')) return 'ozon';
  if (s.includes('wildberries') || s.includes('вайлдберриз') || s.includes('wb'))
    return 'wildberries';
  if (s.includes('яндекс') || s.includes('yandex')) return 'yandex';
  if (
    s.includes('мегамаркет') ||
    s.includes('megamarket') ||
    s.includes('сбермегамаркет') ||
    s.includes('sbermegamarket')
  )
    return 'megamarket';
  if (s.includes('магнит') || s.includes('magnit') || s.includes('kazan')) return 'magnit';
  if (s.includes('холодильник') || s.includes('holodilnik')) return 'holodilnik';
  if (
    s.includes('aliexpress') ||
    s.includes('алиэкспресс') ||
    s.includes('алиекспресс') ||
    s.includes('ali')
  )
    return 'aliexpress';
  return null;
};

export const detectPlatform = (sourceStr) => {
  if (!sourceStr) return null;
  const str = sourceStr.toLowerCase();
  if (str.includes('→')) {
    const lastPart = str.split('→').pop().trim();
    const matched = matchPlatformToken(lastPart);
    if (matched) return matched;
  }
  return matchPlatformToken(str);
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