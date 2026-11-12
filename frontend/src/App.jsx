import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from './hooks/useAuth';
import { useProducts } from './hooks/useProducts';
import { useMigration } from './hooks/useMigration';
import TopBar from './components/layout/TopBar';
import Sidebar from './components/layout/Sidebar';
import Landing from './components/layout/Landing';
import AuthModal from './components/auth/AuthModal';
import Alert from './components/common/Alert';
import Button from './components/common/Button';
import Icon from './components/icons';
import StatsGrid from './components/products/StatsGrid';
import ImportModal from './components/import/ImportModal';
import MigrateModal from './components/migration/MigrateModal';
import BatchMigrateModal from './components/migration/BatchMigrateModal';
import ExportModal from './components/export/ExportModal';
import AttributesModal from './components/products/AttributesModal';
import VariantsModal from './components/products/VariantsModal';
import PhotosModal from './components/products/PhotosModal';
import EmailVerificationBanner from './components/layout/EmailVerificationBanner';
import { api } from './api';
import './App.css';
import EmptyState from './components/common/EmptyState';
import OnboardingTour from './components/onboarding/OnboardingTour';
import LogisticsModal from './components/products/LogisticsModal';
import ProductsPage from './pages/ProductsPage';

/* ✅ О4: code-splitting — редко открываемые страницы выгружаются в отдельные
 * чанки и грузятся при первом заходе. Дефолтный вид «products» и модалки
 * остаются в главном чанке: они нужны сразу после логина. */
const CategoryMapping = lazy(() => import('./CategoryMapping'));
const HistoryView = lazy(() => import('./components/history/HistoryView'));
const StatsDashboard = lazy(() => import('./components/dashboard/StatsDashboard'));
const SpecsPage = lazy(() => import('./pages/SpecsPage'));
const SpecsMonitorPage = lazy(() => import('./pages/SpecsMonitorPage'));
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'));
const HelpPage = lazy(() => import('./pages/HelpPage'));
const PrivacyPolicyPage = lazy(() =>
  import('./pages/Legal').then((m) => ({ default: m.PrivacyPolicyPage }))
);
const TermsOfUsePage = lazy(() => import('./pages/Legal').then((m) => ({ default: m.TermsOfUsePage })));
const VerifyEmailPage = lazy(() =>
  import('./pages/EmailPages').then((m) => ({ default: m.VerifyEmailPage }))
);
const ForgotPasswordPage = lazy(() =>
  import('./pages/EmailPages').then((m) => ({ default: m.ForgotPasswordPage }))
);
const ResetPasswordPage = lazy(() =>
  import('./pages/EmailPages').then((m) => ({ default: m.ResetPasswordPage }))
);

/* Заглушка Suspense: единый стиль с внутристранничными спиннерами */
const ViewFallback = () => (
  <div className="card">
    <div className="loading-spinner">
      <div className="spinner" />
      <p style={{ color: 'var(--text-secondary)' }}>Загрузка...</p>
    </div>
  </div>
);

/* ==================== Представления рабочих маршрутов ==================== */

const DashboardView = ({ stats, onGoImport }) => {
  const hasProducts = stats && stats.total > 0;
  return (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">Дашборд</h1>
          <p className="header-subtitle">Обзор миграции товаров</p>
        </div>
      </header>
      {hasProducts ? (
        <>
          <StatsGrid stats={stats} />
          <Suspense fallback={<ViewFallback />}>
            <StatsDashboard />
          </Suspense>
        </>
      ) : (
        <EmptyState
          icon={<Icon name="dashboard" size={48} />}
          title="Статистика появится после первой операции"
          description="Импортируйте товары — и дашборд покажет сводку по статусам и источникам."
          actionLabel="Перейти к импорту"
          onAction={onGoImport}
        />
      )}
    </>
  );
};

const ImportView = ({ onOpenImportModal }) => (
  <>
    <header className="header">
      <div>
        <h1 className="header-title">Импорт товаров</h1>
        <p className="header-subtitle">Загрузка карточек из файлов или по API</p>
      </div>
    </header>
    <div className="import-quick-actions">
      <div
        className="card import-card"
        role="button"
        tabIndex={0}
        onClick={onOpenImportModal}
        onKeyDown={(e) => e.key === 'Enter' && onOpenImportModal()}
      >
        <div className="import-card-icon">
          <Icon name="import" size={44} />
        </div>
        <h3>Из Excel / CSV</h3>
        <p>
          Рекомендуемый способ: выгрузка из кабинета Ozon, WB, Яндекс Маркет или Магнит Маркет
        </p>
        <Button>Выбрать файл</Button>
      </div>
      <div
        className="card import-card"
        role="button"
        tabIndex={0}
        onClick={onOpenImportModal}
        onKeyDown={(e) => e.key === 'Enter' && onOpenImportModal()}
      >
        <div className="import-card-icon">
          <Icon name="key" size={44} />
        </div>
        <h3>По API ключу / YML</h3>
        <p>Ozon, Wildberries, Яндекс Маркет. Тест-ключ: test:test</p>
        <Button>Ввести ключ</Button>
      </div>
    </div>
  </>
);

/* Публичные маршруты с query-параметрами (token из ссылки из письма) */
const VerifyEmailRoute = () => {
  const [params] = useSearchParams();
  return (
    <Suspense fallback={<ViewFallback />}>
      <VerifyEmailPage token={params.get('token')} />
    </Suspense>
  );
};

const ForgotPasswordRoute = () => (
  <Suspense fallback={<ViewFallback />}>
    <ForgotPasswordPage />
  </Suspense>
);

const ResetPasswordRoute = () => {
  const [params] = useSearchParams();
  return (
    <Suspense fallback={<ViewFallback />}>
      <ResetPasswordPage token={params.get('token')} />
    </Suspense>
  );
};

/* Вкладки, которые имели смысл до роутинга: для редиректа с «/» в последнюю
 * открытую (localStorage 'marketplace_active_view' — старые значения
 * 1:1 совпадают с именами маршрутов). */
const KNOWN_VIEWS = [
  'dashboard',
  'products',
  'import',
  'mapping',
  'specs',
  'specs-monitor',
  'templates',
  'history',
];

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { authChecked, isAuthenticated, user, handleLogin, handleLogout } = useAuth();
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
  const [authTab, setAuthTab] = useState(null);
  const [message, setMessage] = useState('');

  // Последняя открытая вкладка: пишем при каждой навигации (только в рабочем
  // режиме), для редиректа с «/» читаем localStorage в момент рендера роута —
  // без memo, чтобы после «логаут → повторный вход» (App не перемонтируется,
  // а при логауте вкладка сбрасывается на «Товары») редирект видел свежие
  // данные, а не застарелый результат useMemo.
  const getHomeRedirect = () => {
    const saved = localStorage.getItem('marketplace_active_view');
    return `/${KNOWN_VIEWS.includes(saved) ? saved : 'products'}`;
  };

  useEffect(() => {
    if (isAuthenticated) {
      const view = location.pathname.replace(/^\//, '');
      if (view) localStorage.setItem('marketplace_active_view', view);
    }
  }, [location, isAuthenticated]);

  // Модалки
  const [showImportModal, setShowImportModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showBatchModal, setShowBatchModal] = useState(false);
  // ✅ Храним сам объект товара (свежий из строки таблицы), а не только ID:
  // у App свой кэш-список (useProducts, первые 50), который мог не обновиться —
  // раньше для товара вне этой выборки модалка вообще не открывалась,
  // а для «старого» товара показывала устаревшую цену (баг цены 0).
  const [migrateTarget, setMigrateTarget] = useState(null);
  const [selectedProductIds, setSelectedProductIds] = useState([]);

  // Модалки редактирования товара
  const [editAttributesProduct, setEditAttributesProduct] = useState(null);
  const [editVariantsProduct, setEditVariantsProduct] = useState(null);
  const [editPhotosProduct, setEditPhotosProduct] = useState(null);
  const [editLogisticsProduct, setEditLogisticsProduct] = useState(null);

  // ==================== Эффекты ====================
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Выход/логаут: закрыть модалки и вернуть следующую сессию к «Товарам»
  // (раньше это делал setCurrentView('products'))
  useEffect(() => {
    if (!isAuthenticated) {
      setMessage('');
      setSelectedProductIds([]);
      setShowImportModal(false);
      setShowExportModal(false);
      setShowBatchModal(false);
      setMigrateTarget(null);
      setEditAttributesProduct(null);
      setEditVariantsProduct(null);
      setEditPhotosProduct(null);
      setEditLogisticsProduct(null);
      localStorage.setItem('marketplace_active_view', 'products');
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!message) return undefined;
    const t = setTimeout(() => setMessage(''), 6000);
    return () => clearTimeout(t);
  }, [message]);

  // ==================== Хуки данных ====================
  const {
    products,
    stats,
    loading: productsLoading,
    loadData,
    getProductById,
  } = useProducts(isAuthenticated, handleLogout);

  const { isMigratingProductId, migrateProduct, migrateBatch, pollBatchProgress } = useMigration(
    loadData,
    setMessage
  );

  // ОБЪЯДИНЁННАЯ функция перезагрузки (Round 7: вместо refreshKey-проброса —
  // инвалидация кэша TanStack Query; подписчики ['products'], ['stats'],
  // ['gaps'], ['spec-names'], ['edit-history'] перезапросятся сами).
  const refreshAll = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['products'] });
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['stats'] }),
      queryClient.invalidateQueries({ queryKey: ['gaps'] }),
      queryClient.invalidateQueries({ queryKey: ['spec-names'] }),
      queryClient.invalidateQueries({ queryKey: ['edit-history'] }),
    ]);
  }, [queryClient]);

  // ==================== Обработчики импорта ====================
  const handleImport = useCallback(
    async (fullKey) => {
      try {
        const data = await api.importProducts(fullKey);
        if (data.success) {
          setMessage(`✅ Импортировано ${data.imported} товаров${data.is_mock ? ' (тест)' : ''}`);
          setShowImportModal(false);
          await refreshAll();
        } else {
          setMessage('❌ Ошибка импорта: ' + (data.detail || 'неизвестно'));
        }
      } catch (e) {
        setMessage('❌ ' + e.message);
      }
    },
    [refreshAll]
  );

  const handleFileImport = useCallback(
    async (platform, file, mode = 'create') => {
      try {
        const data = await api.importFromFile(platform, file, mode);
        if (data.success) {
          let msg = `✅ ${data.message || `Импортировано ${data.imported} товаров`}`;
          if (data.updated) msg += ` · обновлено: ${data.updated}`;
          setMessage(msg);
          setShowImportModal(false);
          await refreshAll();
        } else {
          setMessage('❌ ' + (data.detail || 'Ошибка импорта'));
        }
      } catch (e) {
        setMessage('❌ ' + e.message);
      }
    },
    [refreshAll]
  );

  // ==================== Обработчики миграции ====================
  const handleConfirmMigrate = useCallback(
    async (id, platform, edited, autoExport = true) => {
      setMigrateTarget(null);
      try {
        await migrateProduct(id, platform, edited);
        setMessage('✅ Карточка мигрирована');

        if (autoExport) {
          try {
            await api.exportXlsxV2(platform, 'success', id);
            setMessage(
              `✅ Карточка перенесена. Файл для ${platform} скачан — загрузите его в кабинете площадки.`
            );
          } catch (e) {
            setMessage(`✅ Карточка перенесена, но файл не скачался: ${e.message}`);
          }
        }
        await refreshAll();
      } catch (e) {
        setMessage(`❌ Ошибка миграции: ${e.message}`);
      }
    },
    [migrateProduct, refreshAll]
  );

  const handleAutoExport = useCallback(
    async (platform) => {
      try {
        const idsToExport = selectedProductIds.length > 0 ? selectedProductIds : null;
        await api.exportXlsxV2(platform, 'success', idsToExport, false);
        setMessage(`✅ Файл для ${platform} скачан — загрузите его в кабинете площадки.`);
        await refreshAll();
      } catch (e) {
        setMessage('❌ Не удалось скачать файл: ' + e.message);
      }
    },
    [refreshAll, selectedProductIds]
  );

  const handleCloseBatchModal = useCallback(() => {
    setShowBatchModal(false);
    setSelectedProductIds([]);
    refreshAll();
  }, [refreshAll]);

  const handleStartBatchMigration = useCallback(
    async (ids, platform) => {
      return await migrateBatch(ids, platform);
    },
    [migrateBatch]
  );

  // Товар в окно миграции: объект из строки таблицы (свежий) — приоритетнее
  // устаревшего App-списка; fallback — поиск по App-списку для вызовов по ID.
  const handleProductsPageMigrate = useCallback(
    (target) => {
      if (Array.isArray(target)) {
        setSelectedProductIds(target);
        setShowBatchModal(true);
      } else if (target && target.id) {
        setMigrateTarget(target);
      } else if (typeof target === 'number') {
        setMigrateTarget(products.find((p) => p.id === target) || { id: target });
      }
    },
    [products]
  );

  // ==================== Обработчики экспорта ====================
  const handleExportForPlatform = useCallback(
    async (platform, status, activeIds = null, changedSince = false) => {
      try {
        const filename = await api.exportXlsxV2(platform, status, activeIds, changedSince);
        setMessage(
          changedSince
            ? `✅ Скачан файл с новыми/изменёнными товарами (${platform}). Загрузите его в кабинете площадки.`
            : filename && filename.toLowerCase().endsWith('.zip')
              ? `✅ Скачан ZIP из нескольких файлов. Загрузите каждый в кабинете ${platform}.`
              : `✅ Файл по шаблону ${platform} скачан. Загрузите его в кабинете площадки.`
        );
        setShowExportModal(false);
        await refreshAll();
      } catch (e) {
        setMessage(`❌ ${e.message}`);
      }
    },
    [refreshAll]
  );

  const handleOpenExport = useCallback((ids) => {
    if (Array.isArray(ids)) {
      setSelectedProductIds(ids);
    }
    setShowExportModal(true);
  }, []);

  // ==================== Обработчики авторизации ====================
  const openAuth = useCallback((tab) => setAuthTab(tab || 'login'), []);

  // ==================== Обработчики редактирования товара ====================
  const handleEditAttributes = useCallback((product) => {
    setMessage('');
    setEditAttributesProduct(product);
  }, []);

  const handleEditVariants = useCallback((product) => {
    setMessage('');
    setEditVariantsProduct(product);
  }, []);

  const handleEditPhotos = useCallback((product) => {
    setMessage('');
    setEditPhotosProduct(product);
  }, []);

  const handleEditLogistics = useCallback((product) => {
    setMessage('');
    setEditLogisticsProduct(product);
  }, []);

  // ==================== Пока не знаем, залогинены ли — тишина ====================
  // (раньше до ответа /auth/me мигал лендинг для залогиненного пользователя)
  if (!authChecked) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      </div>
    );
  }

  // ==================== Гостевой режим ====================
  if (!isAuthenticated) {
    return (
      <div className="public-layout">
        <TopBar isAuthenticated={false} onOpenAuth={openAuth} />
        <Routes>
          <Route path="/" element={<Landing onOpenAuth={openAuth} />} />
          <Route
            path="/privacy"
            element={
              <Suspense fallback={<ViewFallback />}>
                <PrivacyPolicyPage />
              </Suspense>
            }
          />
          <Route
            path="/terms"
            element={
              <Suspense fallback={<ViewFallback />}>
                <TermsOfUsePage />
              </Suspense>
            }
          />
          <Route
            path="/help"
            element={
              <Suspense fallback={<ViewFallback />}>
                <HelpPage />
              </Suspense>
            }
          />
          <Route path="/verify-email" element={<VerifyEmailRoute />} />
          <Route path="/forgot-password" element={<ForgotPasswordRoute />} />
          <Route path="/reset-password" element={<ResetPasswordRoute />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <AuthModal
          isOpen={!!authTab}
          initialTab={authTab || 'login'}
          onClose={() => setAuthTab(null)}
          onLogin={handleLogin}
        />
      </div>
    );
  }

  // ==================== Рабочий режим ====================
  return (
    <div className="app-layout">
      <TopBar
        isAuthenticated
        user={user}
        onOpenAuth={openAuth}
        onLogout={handleLogout}
        onOpenHistory={() => navigate('/history')}
      />

      <EmailVerificationBanner user={user} />
      <OnboardingTour />

      <div className="app-body">
        <Sidebar theme={theme} setTheme={setTheme} isAdmin={user?.role === 'admin'} />
        <main className="main-content" data-onboarding="welcome">
          <Alert message={message} onClose={() => setMessage('')} />
          <Routes>
            <Route path="/" element={<Navigate to={getHomeRedirect()} replace />} />
            <Route
              path="/dashboard"
              element={<DashboardView stats={stats} onGoImport={() => navigate('/import')} />}
            />
            <Route path="/import" element={<ImportView onOpenImportModal={() => setShowImportModal(true)} />} />
            <Route
              path="/mapping"
              element={
                <Suspense fallback={<ViewFallback />}>
                  <CategoryMapping onBack={() => navigate('/products')} />
                </Suspense>
              }
            />
            <Route
              path="/specs"
              element={
                <Suspense fallback={<ViewFallback />}>
                  <SpecsPage
                    user={user}
                    onNotify={setMessage}
                    onOpenMonitor={() => navigate('/specs-monitor')}
                  />
                </Suspense>
              }
            />
            {/* Мониторинг спеков — только админ; остальным тихий редирект */}
            <Route
              path="/specs-monitor"
              element={
                user?.role === 'admin' ? (
                  <Suspense fallback={<ViewFallback />}>
                    <SpecsMonitorPage user={user} />
                  </Suspense>
                ) : (
                  <Navigate to="/products" replace />
                )
              }
            />
            <Route
              path="/templates"
              element={
                <Suspense fallback={<ViewFallback />}>
                  <TemplatesPage onNotify={setMessage} />
                </Suspense>
              }
            />
            <Route
              path="/history"
              element={
                <Suspense fallback={<ViewFallback />}>
                  <HistoryView />
                </Suspense>
              }
            />
            <Route
              path="/products"
              element={
                <ProductsPage
                  isAdmin={user?.role === 'admin'}
                  onMigrate={handleProductsPageMigrate}
                  onLogistics={handleEditLogistics}
                  onAttributes={handleEditAttributes}
                  onVariants={handleEditVariants}
                  onPhotos={handleEditPhotos}
                  onExport={handleOpenExport}
                  onImport={() => setShowImportModal(true)}
                />
              }
            />
            <Route path="*" element={<Navigate to="/products" replace />} />
          </Routes>
        </main>
      </div>

      {/* ==================== Модалки ==================== */}
      <ImportModal
        key={`import-${showImportModal}`}
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImport={handleImport}
        onFileImport={handleFileImport}
        loading={productsLoading}
      />

      {migrateTarget && (
        <MigrateModal
          key={`migrate-${migrateTarget.id}`}
          isOpen
          onClose={() => setMigrateTarget(null)}
          product={getProductById(migrateTarget.id) || migrateTarget}
          onConfirm={handleConfirmMigrate}
          onSaved={refreshAll}
          onNotify={setMessage}
          loading={isMigratingProductId === migrateTarget.id}
        />
      )}

      <BatchMigrateModal
        key={`batch-${selectedProductIds.join('-')}`}
        isOpen={showBatchModal}
        onAutoExport={handleAutoExport}
        onClose={handleCloseBatchModal}
        selectedIds={selectedProductIds}
        onStartMigration={handleStartBatchMigration}
        pollProgress={pollBatchProgress}
        loading={productsLoading}
      />

      <ExportModal
        key={`export-${showExportModal}-${selectedProductIds.join('-')}`}
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
        onExport={handleExportForPlatform}
        selectedIds={selectedProductIds}
        loading={productsLoading}
        onOpenTemplates={() => navigate('/templates')}
      />

      {editLogisticsProduct && (
        <LogisticsModal
          key={`logistics-${editLogisticsProduct.id}`}
          isOpen
          onClose={() => setEditLogisticsProduct(null)}
          product={getProductById(editLogisticsProduct.id) || editLogisticsProduct}
          onSaved={refreshAll}
        />
      )}

      {editAttributesProduct && (
        <AttributesModal
          key={`attrs-${editAttributesProduct.id}`}
          isOpen
          onClose={() => setEditAttributesProduct(null)}
          product={getProductById(editAttributesProduct.id) || editAttributesProduct}
          onSave={refreshAll}
          onNotify={setMessage}
        />
      )}

      {editVariantsProduct && (
        <VariantsModal
          key={`variants-${editVariantsProduct.id}`}
          isOpen
          onClose={() => setEditVariantsProduct(null)}
          product={getProductById(editVariantsProduct.id) || editVariantsProduct}
          onSave={refreshAll}
        />
      )}

      {editPhotosProduct && (
        <PhotosModal
          key={`photos-${editPhotosProduct.id}`}
          isOpen
          onClose={() => setEditPhotosProduct(null)}
          product={getProductById(editPhotosProduct.id) || editPhotosProduct}
          onSave={refreshAll}
          onNotify={setMessage}
        />
      )}

      <AuthModal
        isOpen={!!authTab}
        initialTab={authTab || 'login'}
        onClose={() => setAuthTab(null)}
        onLogin={handleLogin}
      />
    </div>
  );
}

export default App;
