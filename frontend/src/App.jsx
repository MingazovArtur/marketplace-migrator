import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
import ProductTable from './components/products/ProductTable';
import SearchBar from './components/common/SearchBar';
import Pagination from './components/common/Pagination';
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
import { api } from './api';
import './App.css';

function App() {
  const { token, isAuthenticated, user, handleLogin, handleLogout } = useAuth();

  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
  const [authTab, setAuthTab] = useState(null); // null | 'login' | 'register'
  const [message, setMessage] = useState('');
  const [currentView, setCurrentView] = useState('products');

  const [showImportModal, setShowImportModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [migrateProductId, setMigrateProductId] = useState(null);
  const [selectedProductIds, setSelectedProductIds] = useState([]);

  const [editAttributesProduct, setEditAttributesProduct] = useState(null);
  const [editVariantsProduct, setEditVariantsProduct] = useState(null);
  const [editPhotosProduct, setEditPhotosProduct] = useState(null);

  // Тема применяется к <html> — фон body всегда совпадает с темой
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Сброс состояния при выходе
  useEffect(() => {
    if (!token) {
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
      setCurrentView('products');
    }
  }, [token]);

  // Сообщение само исчезает через 6 секунд
  useEffect(() => {
    if (!message) return undefined;
    const t = setTimeout(() => setMessage(''), 6000);
    return () => clearTimeout(t);
  }, [message]);

  const {
    products, stats, loading: productsLoading, loadData, availableForBatch,
    getProductById, totalProducts, filters, updateFilters, setPage,
  } = useProducts(token, handleLogout);

  const { isMigratingProductId, migrateProduct, migrateBatch, pollBatchProgress } =
    useMigration(loadData, setMessage);

  // Уникальные источники для фильтра в SearchBar
  const sources = useMemo(
    () => Array.from(new Set(products.map((p) => p.source).filter(Boolean))).sort(),
    [products]
  );

  /* ================= обработчики ================= */

  const handleImport = useCallback(async (fullKey) => {
    try {
      const data = await api.importProducts(fullKey);
      if (data.success) {
        setMessage(`✅ Импортировано ${data.imported} товаров${data.is_mock ? ' (тест)' : ''}`);
        setShowImportModal(false);
        loadData();
      } else {
        setMessage('❌ Ошибка импорта: ' + (data.detail || 'неизвестно'));
      }
    } catch (e) {
      setMessage('❌ ' + e.message);
    }
  }, [loadData]);

  const handleFileImport = useCallback(async (platform, file, mode = 'create') => {
    try {
      const data = await api.importFromFile(platform, file, mode);
      if (data.success) {
        let msg = `✅ ${data.message || `Импортировано ${data.imported} товаров`}`;
        if (data.updated) msg += ` · обновлено: ${data.updated}`;
        setMessage(msg);
        setShowImportModal(false);
        loadData();
      } else {
        setMessage('❌ ' + (data.detail || 'Ошибка импорта'));
      }
    } catch (e) {
      setMessage('❌ ' + e.message);
    }
  }, [loadData]);

  const handleOpenMigrateModal = useCallback((id) => setMigrateProductId(id), []);

  const handleConfirmMigrate = useCallback(async (id, platform, edited, autoExport = true) => {
    setMigrateProductId(null);
    await migrateProduct(id, platform, edited);
    if (autoExport) {
      try {
        await api.exportForPlatform(platform, 'success');
        setMessage(`✅ Карточка перенесена. Файл для ${platform} скачан — загрузите его в кабинете площадки.`);
      } catch (e) {
        setMessage(`✅ Карточка перенесена, но файл не скачался: ${e.message}`);
      }
    }
  }, [migrateProduct]);

    /* Автовыгрузка после пакетной миграции */
  const handleAutoExport = useCallback(async (platform) => {
    try {
      await api.exportForPlatform(platform, 'success');
      setMessage(`📥 Файл для ${platform} скачан — загрузите его в кабинете площадки.`);
      loadData();
    } catch (e) {
      setMessage('❌ Не удалось скачать файл: ' + e.message);
    }
  }, [loadData]);

  const toggleProductSelection = useCallback((id) => {
    setSelectedProductIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (selectedProductIds.length === availableForBatch && availableForBatch > 0) {
      setSelectedProductIds([]);
    } else {
      setSelectedProductIds(
        products
          .filter(p => p.status !== 'success' && p.status !== 'processing')
          .map(p => p.id)
      );
    }
  }, [selectedProductIds.length, availableForBatch, products]);

  const handleOpenBatchModal = useCallback(() => {
    if (!selectedProductIds.length) {
      setMessage('⚠️ Выберите хотя бы один товар');
      return;
    }
    setShowBatchModal(true);
  }, [selectedProductIds.length]);

  const hasActiveFilters =
    (filters.status && filters.status !== 'all') ||
    (filters.source && filters.source !== 'all') ||
    !!filters.search ||
    (filters.sort && filters.sort !== 'newest');

  const resetFilters = useCallback(() => {
    updateFilters({ status: 'all', source: 'all', search: '', sort: 'newest' });
  }, [updateFilters]);

  const handleCloseBatchModal = useCallback(() => {
    setShowBatchModal(false);
    setSelectedProductIds([]);
    loadData();
  }, [loadData]);

  const handleStartBatchMigration = useCallback(async (ids, platform) => {
    // ✅ НЕ закрываем модалку: ошибку покажет сама BatchMigrateModal
    return await migrateBatch(ids, platform);
  }, [migrateBatch]);

  const handleBulkEdit = useCallback(async (payload) => {
    try {
      const data = await api.bulkUpdateProducts(payload);
      setMessage(`✅ Обновлено товаров: ${data.updated}`);
      setShowBulkModal(false);
      setSelectedProductIds([]);
      loadData();
    } catch (e) {
      setMessage('❌ ' + e.message);
    }
  }, [loadData]);

  const handleExportReport = useCallback(async () => {
    if (!stats || stats.total === 0) {
      setMessage('⚠️ Нет товаров для экспорта.');
      return;
    }
    try {
      await api.exportReport();
      setMessage('✅ Отчет успешно скачан!');
    } catch (e) {
      setMessage('❌ Ошибка при скачивании отчета: ' + e.message);
    }
  }, [stats]);

  const handleExportForPlatform = useCallback(async (platform, status) => {
    try {
      await api.exportForPlatform(platform, status);
      setMessage(`✅ Файл для ${platform} скачан. Загрузите его в кабинете площадки.`);
      setShowExportModal(false);
    } catch (e) {
      setMessage('❌ ' + e.message);
    }
  }, []);

  const openAuth = useCallback((tab) => setAuthTab(tab || 'login'), []);

  const handleEditAttributes = useCallback((product) => setEditAttributesProduct(product), []);
  const handleEditVariants = useCallback((product) => setEditVariantsProduct(product), []);
  const handleEditPhotos = useCallback((product) => setEditPhotosProduct(product), []);

  /* ================= виды ================= */

  const renderDashboard = () => (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">Дашборд</h1>
          <p className="header-subtitle">Обзор миграции товаров</p>
        </div>
      </header>
      <StatsGrid stats={stats} />
      <StatsDashboard />
    </>
  );

  const renderProducts = () => (
    <>
      <header className="header">
        <div>
          <h1 className="header-title">Товары</h1>
          <p className="header-subtitle">Управление карточками товаров</p>
        </div>
        <div className="header-actions">
          <Button onClick={() => setShowImportModal(true)}>
            <Icon name="import" size={16} /> Импорт
          </Button>
          <Button variant="secondary" onClick={() => setShowExportModal(true)}>
            <Icon name="export" size={16} /> Выгрузка
          </Button>
          <Button
            variant="secondary"
            onClick={handleExportReport}
            disabled={!stats || stats.total === 0}
          >
            <Icon name="report" size={16} /> Отчет (Excel)
          </Button>
        </div>
      </header>

      <StatsGrid stats={stats} />
      <SearchBar filters={filters} updateFilters={updateFilters} sources={sources} />

      <div className="products-toolbar">
        <Button
          variant="secondary"
          onClick={() => setShowBulkModal(true)}
          disabled={!selectedProductIds.length}
        >
          <Icon name="edit" size={16} /> Редактировать ({selectedProductIds.length})
        </Button>
        <Button onClick={handleOpenBatchModal} disabled={!selectedProductIds.length}>
          <Icon name="migrate" size={16} /> Перенести выбранные ({selectedProductIds.length})
        </Button>
      </div>

      <ProductTable
        products={products}
        selectedIds={selectedProductIds}
        isMigratingProductId={isMigratingProductId}
        loading={productsLoading}
        availableForBatch={availableForBatch}
        onSelect={toggleProductSelection}
        onSelectAll={toggleSelectAll}
        onMigrate={handleOpenMigrateModal}
        onEditAttributes={handleEditAttributes}
        onEditVariants={handleEditVariants}
        onEditPhotos={handleEditPhotos}
        hasActiveFilters={hasActiveFilters}
        onResetFilters={resetFilters}
      />
      <Pagination
        total={totalProducts}
        skip={filters.skip}
        limit={filters.limit}
        onPageChange={setPage}
      />

      <AttributesModal
        isOpen={!!editAttributesProduct}
        onClose={() => setEditAttributesProduct(null)}
        product={editAttributesProduct}
        onSave={loadData}
      />
      <VariantsModal
        isOpen={!!editVariantsProduct}
        onClose={() => setEditVariantsProduct(null)}
        product={editVariantsProduct}
        onSave={loadData}
      />
      <PhotosModal
        isOpen={!!editPhotosProduct}
        onClose={() => setEditPhotosProduct(null)}
        product={editPhotosProduct}
        onSave={loadData}
        onNotify={setMessage}
      />
    </>
  );

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
          <p>Рекомендуемый способ: выгрузка из кабинета Ozon, WB, Яндекс Маркет или Магнит Маркет</p>
          <Button>Выбрать файл</Button>
        </div>
        <div
          className="card import-card"
          role="button"
          tabIndex={0}
          onClick={() => setShowImportModal(true)}
          onKeyDown={(e) => e.key === 'Enter' && setShowImportModal(true)}
        >
          <div className="import-card-icon">🔑</div>
          <h3>По API ключу / YML</h3>
          <p>Ozon, Wildberries, Яндекс Маркет. Тест-ключ: test:test</p>
          <Button>Ввести ключ</Button>
        </div>
      </div>
    </>
  );

  const renderView = () => {
    switch (currentView) {
      case 'dashboard': return renderDashboard();
      case 'import': return renderImport();
      case 'mapping': return <CategoryMapping onBack={() => setCurrentView('products')} />;
      case 'history': return <HistoryView />;
      default: return renderProducts();
    }
  };

  /* ================= гостевой режим ================= */

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

  /* ================= рабочий режим ================= */

  return (
    <div className="app-layout">
      <TopBar
        isAuthenticated
        user={user}
        onOpenAuth={openAuth}
        onLogout={handleLogout}
        onOpenHistory={() => setCurrentView('history')}
      />

      <div className="app-body">
        <Sidebar
          currentView={currentView}
          setCurrentView={setCurrentView}
          theme={theme}
          setTheme={setTheme}
        />
        <main className="main-content">
          <Alert message={message} onClose={() => setMessage('')} />
          {renderView()}
        </main>
      </div>

      {/* модалки операций */}
      <ImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImport={handleImport}
        onFileImport={handleFileImport}
        loading={productsLoading}
      />
      <MigrateModal
        isOpen={!!migrateProductId}
        onClose={() => setMigrateProductId(null)}
        product={getProductById(migrateProductId)}
        onConfirm={handleConfirmMigrate}
        loading={isMigratingProductId === migrateProductId}
      />
      <BatchMigrateModal
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
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
        onExport={handleExportForPlatform}
        loading={productsLoading}
      />
      <BulkEditModal
        isOpen={showBulkModal}
        onClose={() => setShowBulkModal(false)}
        selectedIds={selectedProductIds}
        onSubmit={handleBulkEdit}
        loading={productsLoading}
      />
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