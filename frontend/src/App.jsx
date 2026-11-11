import React, { useState, useEffect, useCallback } from 'react';
import CategoryMapping from './CategoryMapping';
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
import BulkEditModal from './components/products/BulkEditModal';
import AttributesModal from './components/products/AttributesModal';
import VariantsModal from './components/products/VariantsModal';
import PhotosModal from './components/products/PhotosModal';
import HistoryView from './components/history/HistoryView';
import StatsDashboard from './components/dashboard/StatsDashboard';
import EmailVerificationBanner from './components/layout/EmailVerificationBanner';
import { PrivacyPolicyPage, TermsOfUsePage } from './pages/Legal';
import { VerifyEmailPage, ForgotPasswordPage, ResetPasswordPage } from './pages/EmailPages';
import HelpPage from './pages/HelpPage';
import { api } from './api';
import './App.css';
import EmptyState from './components/common/EmptyState';
import OnboardingTour from './components/onboarding/OnboardingTour';
import LogisticsModal from './components/products/LogisticsModal';
import SpecsPage from './pages/SpecsPage';
import SpecsMonitorPage from './pages/SpecsMonitorPage';
import ProductsPage from './pages/ProductsPage';
import TemplatesPage from './pages/TemplatesPage';

function App() {
  const [hash, setHash] = useState(window.location.hash);
  const { authChecked, isAuthenticated, user, handleLogin, handleLogout } = useAuth();
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
  const [authTab, setAuthTab] = useState(null);
  const [message, setMessage] = useState('');
  
  // ✅ Сохранение текущей вкладки в localStorage с фоллбэком на 'products'
  const [currentView, setCurrentView] = useState(() => {
    return localStorage.getItem('marketplace_active_view') || 'products';
  });

  useEffect(() => {
    localStorage.setItem('marketplace_active_view', currentView);
  }, [currentView]);

  // Триггер синхронизации обоих списков товаров (App + ProductsPage)
  const [refreshKey, setRefreshKey] = useState(0);

  // Модалки
  const [showImportModal, setShowImportModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [migrateProductId, setMigrateProductId] = useState(null);
  const [selectedProductIds, setSelectedProductIds] = useState([]);

  // Модалки редактирования товара
  const [editAttributesProduct, setEditAttributesProduct] = useState(null);
  const [editVariantsProduct, setEditVariantsProduct] = useState(null);
  const [editPhotosProduct, setEditPhotosProduct] = useState(null);
  const [editLogisticsProduct, setEditLogisticsProduct] = useState(null);

  // ==================== Эффекты ====================
  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  useEffect(() => {
    if (!isAuthenticated) {
      setMessage('');
      setSelectedProductIds([]);
      setShowImportModal(false);
      setShowExportModal(false);
      setShowBulkModal(false);
      setShowBatchModal(false);
      setMigrateProductId(null);
      setEditAttributesProduct(null);
      setEditVariantsProduct(null);
      setEditPhotosProduct(null);
      setEditLogisticsProduct(null);
      setCurrentView('products');
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

  // ОБЪЕДИНЁННАЯ функция перезагрузки:
  // обновляет App-овский список (useProducts) И внутренний список ProductsPage через refreshKey.
  const refreshAll = useCallback(async () => {
    try {
      await loadData();
    } finally {
      setRefreshKey((k) => k + 1);
    }
  }, [loadData]);

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
      setMigrateProductId(null);
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
        await api.exportXlsxV2(platform, 'success', idsToExport);
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

  const handleProductsPageMigrate = useCallback((target) => {
    if (Array.isArray(target)) {
      setSelectedProductIds(target);
      setShowBatchModal(true);
    } else if (target && target.id) {
      setMigrateProductId(target.id);
    } else if (typeof target === 'number') {
      setMigrateProductId(target);
    }
  }, []);

  // ==================== Обработчики массового обновления и экспорта ====================
  const handleBulkEdit = useCallback(
    async (payload) => {
      try {
        const data = await api.bulkUpdateProducts(payload);
        setMessage(`✅ Обновлено товаров: ${data.updated}`);
        setShowBulkModal(false);
        setSelectedProductIds([]);
        await refreshAll();
      } catch (e) {
        setMessage('❌ ' + e.message);
      }
    },
    [refreshAll]
  );

  const handleExportForPlatform = useCallback(async (platform, status, activeIds = null) => {
    try {
      const filename = await api.exportXlsxV2(platform, status, activeIds);
      setMessage(
        filename && filename.toLowerCase().endsWith('.zip')
          ? `✅ Скачан ZIP из нескольких файлов. Загрузите каждый в кабинете ${platform}.`
          : `✅ Файл по шаблону ${platform} скачан. Загрузите его в кабинете площадки.`
      );
      setShowExportModal(false);
    } catch (e) {
      setMessage(`❌ ${e.message}`);
    }
  }, []);

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

  // ==================== Hash-роутинг (ПОСЛЕ всех хуков!) ====================
  const hashPath = hash.split('?')[0];
  const hashQuery = new URLSearchParams(hash.split('?')[1] || '');

  if (hashPath === '#/privacy') return <PrivacyPolicyPage />;
  if (hashPath === '#/terms') return <TermsOfUsePage />;
  if (hashPath === '#/verify-email') return <VerifyEmailPage token={hashQuery.get('token')} />;
  if (hashPath === '#/forgot-password') return <ForgotPasswordPage />;
  if (hashPath === '#/reset-password') return <ResetPasswordPage token={hashQuery.get('token')} />;
  if (hashPath === '#/help') return <HelpPage />;

  // ==================== Виды ====================
  const renderDashboard = () => {
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
            <StatsDashboard />
          </>
        ) : (
          <EmptyState
            icon={<Icon name="dashboard" size={48} />}
            title="Статистика появится после первой операции"
            description="Импортируйте товары — и дашборд покажет сводку по статусам и источникам."
            actionLabel="Перейти к импорту"
            onAction={() => setCurrentView('import')}
          />
        )}
      </>
    );
  };

  const renderImport = () => (
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
          onClick={() => setShowImportModal(true)}
          onKeyDown={(e) => e.key === 'Enter' && setShowImportModal(true)}
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
          onClick={() => setShowImportModal(true)}
          onKeyDown={(e) => e.key === 'Enter' && setShowImportModal(true)}
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

  const renderView = () => {
    switch (currentView) {
      case 'dashboard':
        return renderDashboard();
      case 'import':
        return renderImport();
      case 'mapping':
        return <CategoryMapping onBack={() => setCurrentView('products')} />;
      case 'history':
        return <HistoryView />;
      case 'specs':
        return <SpecsPage user={user} onNotify={setMessage} onOpenMonitor={() => setCurrentView('specs-monitor')} />;
      case 'specs-monitor':
        return <SpecsMonitorPage user={user} />;
      case 'templates':
        return <TemplatesPage onNotify={setMessage} />;
      case 'products':
        return (
          <ProductsPage
            isAdmin={user?.role === 'admin'}
            refreshKey={refreshKey}
            onMigrate={handleProductsPageMigrate}
            onLogistics={handleEditLogistics}
            onAttributes={handleEditAttributes}
            onVariants={handleEditVariants}
            onPhotos={handleEditPhotos}
            onExport={handleOpenExport}
            onImport={() => setShowImportModal(true)}
          />
        );
      default:
        return renderDashboard();
    }
  };

  // ==================== Гостевой режим ====================
  if (!isAuthenticated) {
    return (
      <div className="public-layout">
        <TopBar isAuthenticated={false} onOpenAuth={openAuth} />
        <Landing onOpenAuth={openAuth} />
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
        onOpenHistory={() => setCurrentView('history')}
      />

      <EmailVerificationBanner user={user} />
      <OnboardingTour />

      <div className="app-body">
        <Sidebar
          currentView={currentView}
          setCurrentView={setCurrentView}
          theme={theme}
          setTheme={setTheme}
          isAdmin={user?.role === 'admin'}
        />
        <main className="main-content" data-onboarding="welcome">
          <Alert message={message} onClose={() => setMessage('')} />
          {renderView()}
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

      {migrateProductId && (
        <MigrateModal
          key={`migrate-${migrateProductId}`}
          isOpen
          onClose={() => setMigrateProductId(null)}
          product={getProductById(migrateProductId)}
          onConfirm={handleConfirmMigrate}
          onSaved={refreshAll}
          onNotify={setMessage}
          loading={isMigratingProductId === migrateProductId}
        />
      )}

      <BatchMigrateModal
        key={`batch-${selectedProductIds.join('-')}`}
        isOpen={showBatchModal}
        onAutoExport={handleAutoExport}
        onClose={handleCloseBatchModal}
        selectedIds={selectedProductIds}
        products={products}
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
        onOpenTemplates={() => setCurrentView('templates')}
      />

      <BulkEditModal
        key={`bulk-${selectedProductIds.join('-')}`}
        isOpen={showBulkModal}
        onClose={() => setShowBulkModal(false)}
        selectedIds={selectedProductIds}
        onSubmit={handleBulkEdit}
        loading={productsLoading}
      />

      {editLogisticsProduct && (
        <LogisticsModal
          key={`logistics-${editLogisticsProduct.id}-${refreshKey}`}
          isOpen
          onClose={() => setEditLogisticsProduct(null)}
          product={getProductById(editLogisticsProduct.id) || editLogisticsProduct}
          onSaved={refreshAll}
        />
      )}

      {editAttributesProduct && (
        <AttributesModal
          key={`attrs-${editAttributesProduct.id}-${refreshKey}`}
          isOpen
          onClose={() => setEditAttributesProduct(null)}
          product={getProductById(editAttributesProduct.id) || editAttributesProduct}
          onSave={refreshAll}
          onNotify={setMessage}
        />
      )}

      {editVariantsProduct && (
        <VariantsModal
          key={`variants-${editVariantsProduct.id}-${refreshKey}`}
          isOpen
          onClose={() => setEditVariantsProduct(null)}
          product={getProductById(editVariantsProduct.id) || editVariantsProduct}
          onSave={refreshAll}
        />
      )}

      {editPhotosProduct && (
        <PhotosModal
          key={`photos-${editPhotosProduct.id}-${refreshKey}`}
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