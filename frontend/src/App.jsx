import React, { useState, useEffect, useCallback } from 'react';
import Auth from './Auth';
import CategoryMapping from './CategoryMapping';
import { useAuth } from './hooks/useAuth';
import { useProducts } from './hooks/useProducts';
import { useMigration } from './hooks/useMigration';
import { useApi } from './hooks/useApi';
import { detectPlatform, PLATFORMS, getUnavailablePlatforms } from './utils/platformUtils';
import Alert from './components/common/Alert';
import Button from './components/common/Button';
import StatsGrid from './components/products/StatsGrid';
import ProductTable from './components/products/ProductTable';
import ImportModal from './components/import/ImportModal';
import MigrateModal from './components/migration/MigrateModal';
import BatchMigrateModal from './components/migration/BatchMigrateModal';
import Sidebar from './components/layout/Sidebar';
import { api } from './api';
import './App.css';

function App() {
  const { token, isAuthenticated, handleLogin, handleLogout } = useAuth();
  const [message, setMessage] = useState('');
  const [currentView, setCurrentView] = useState('products');
  
  const [showImportModal, setShowImportModal] = useState(false);
  const [showCategoryMapping, setShowCategoryMapping] = useState(false);
  const [migrateProductId, setMigrateProductId] = useState(null);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [selectedProductIds, setSelectedProductIds] = useState([]);

  useEffect(() => {
    if (!token) {
      setMessage('');
      setSelectedProductIds([]);
      setShowImportModal(false);
      setShowCategoryMapping(false);
      setMigrateProductId(null);
      setShowBatchModal(false);
    }
  }, [token]);

  const {
    products,
    stats,
    loading: productsLoading,
    loadData,
    availableForBatch,
    getProductById,
    totalProducts,
    filters,
    updateFilters,
    setPage
  } = useProducts(token, handleLogout);

  const {
    isMigratingProductId,
    migrateProduct,
    migrateBatch,
    pollBatchProgress
  } = useMigration(loadData, setMessage);

  const handleImport = useCallback(async (fullKey) => {
    try {
      const data = await api.importProducts(fullKey);
      if (data.success) {
        setMessage(`✅ Импортировано ${data.imported} товаров с ${data.platform_name}${data.is_mock ? ' (тест)' : ''}`);
        setShowImportModal(false);
        loadData();
      }
    } catch (error) {
      setMessage('❌ ' + error.message);
    }
  }, [loadData]);

  const handleFileImport = useCallback(async (platform, file) => {
    try {
      const data = await api.importFromFile(platform, file);
      if (data.success) {
        setMessage(`✅ ${data.message}`);
        setShowImportModal(false);
        loadData();
      }
    } catch (error) {
      setMessage('❌ ' + error.message);
    }
  }, [loadData]);

  const handleOpenMigrateModal = useCallback((productId) => {
    setMigrateProductId(productId);
  }, []);

  const handleConfirmMigrate = useCallback(async (productId, targetPlatform, editedData) => {
    setMigrateProductId(null);
    await migrateProduct(productId, targetPlatform, editedData);
  }, [migrateProduct]);

  const handleOpenBatchModal = useCallback(() => {
    if (selectedProductIds.length === 0) {
      setMessage('⚠️ Выберите хотя бы один товар');
      return;
    }
    setShowBatchModal(true);
  }, [selectedProductIds.length]);

  const handleCloseBatchModal = useCallback(() => {
    setShowBatchModal(false);
    setSelectedProductIds([]);
    loadData();
  }, [loadData]);

  const handleStartBatchMigration = useCallback(async (ids, platform) => {
    try {
      return await migrateBatch(ids, platform);
    } catch (err) {
      setMessage('❌ ' + (err.message || 'Ошибка'));
      setShowBatchModal(false);
      setSelectedProductIds([]);
      return null;
    }
  }, [migrateBatch]);

  const toggleProductSelection = useCallback((productId) => {
    setSelectedProductIds(prev =>
      prev.includes(productId) ? prev.filter(id => id !== productId) : [...prev, productId]
    );
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (selectedProductIds.length === availableForBatch) {
      setSelectedProductIds([]);
    } else {
      const availableProducts = products
        .filter(p => p.status !== 'success' && p.status !== 'processing')
        .map(p => p.id);
      setSelectedProductIds(availableProducts);
    }
  }, [selectedProductIds.length, availableForBatch, products]);

  const handleExport = useCallback(async () => {
    if (stats.total === 0) {
      setMessage('⚠️ Нет товаров для экспорта.');
      return;
    }
    try {
      await api.exportReport();
      setMessage('✅ Отчет скачан!');
    } catch (error) {
      setMessage('❌ Ошибка: ' + error.message);
    }
  }, [stats.total]);

  if (!isAuthenticated) {
    return <Auth onLogin={handleLogin} />;
  }

  if (showCategoryMapping) {
    return <CategoryMapping onBack={() => setShowCategoryMapping(false)} />;
  }

  const productToMigrate = getProductById(migrateProductId);

  // === РЕНДЕР КОНТЕНТА ДЛЯ КАЖДОЙ ВКЛАДКИ ===
  const renderContent = () => {
    switch (currentView) {
      case 'dashboard':
        return (
          <div className="view-content">
            <header className="header">
              <div>
                <h1 className="header-title">Дашборд</h1>
                <p className="header-subtitle">Обзор статистики миграции</p>
              </div>
            </header>
            <StatsGrid stats={stats} />
            <div className="dashboard-summary card">
              <h3>Краткая сводка</h3>
              <div className="summary-grid">
                <div className="summary-item">
                  <span className="summary-label">Всего товаров</span>
                  <span className="summary-value">{stats.total}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Готово к переносу</span>
                  <span className="summary-value">{stats.pending}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Успешно перенесено</span>
                  <span className="summary-value">{stats.success}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Ошибок</span>
                  <span className="summary-value">{stats.error}</span>
                </div>
              </div>
            </div>
          </div>
        );

      case 'products':
        return (
          <div className="view-content">
            <header className="header">
              <div>
                <h1 className="header-title">Товары</h1>
                <p className="header-subtitle">Управление карточками товаров</p>
              </div>
              <div className="header-actions">
                <Button onClick={() => setShowImportModal(true)}>Импорт</Button>
                <Button variant="secondary" onClick={handleExport} disabled={stats.total === 0}>Экспорт</Button>
              </div>
            </header>
            <Alert message={message} onClose={() => setMessage('')} />
            <StatsGrid stats={stats} />
            <div className="table-container">
              <div className="table-header">
                <h2 className="table-title">Список товаров</h2>
                <Button
                  variant="secondary"
                  onClick={handleOpenBatchModal}
                  disabled={selectedProductIds.length === 0}
                >
                  Перенести выбранные ({selectedProductIds.length})
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
              />
            </div>
          </div>
        );

      case 'import':
        return (
          <div className="view-content">
            <header className="header">
              <div>
                <h1 className="header-title">Импорт товаров</h1>
                <p className="header-subtitle">Загрузка карточек с маркетплейсов</p>
              </div>
            </header>
            <div className="import-quick-actions">
              <div className="card import-card" onClick={() => setShowImportModal(true)}>
                <div className="import-card-icon">📥</div>
                <h3>Импорт по API ключу</h3>
                <p>Загрузка через API Ozon, Wildberries или Яндекс Маркет</p>
                <Button variant="primary">Начать импорт</Button>
              </div>
              <div className="card import-card" onClick={() => setShowImportModal(true)}>
                <div className="import-card-icon">📁</div>
                <h3>Импорт из файла</h3>
                <p>Загрузка из Excel (.xlsx) или CSV файла</p>
                <Button variant="primary">Выбрать файл</Button>
              </div>
              <div className="card import-card" onClick={() => setShowImportModal(true)}>
                <div className="import-card-icon"></div>
                <h3>Импорт по YML-ссылке</h3>
                <p>Парсинг YML-фида Яндекс Маркета</p>
                <Button variant="primary">Вставить ссылку</Button>
              </div>
            </div>
          </div>
        );

      case 'mapping':
        return (
          <div className="view-content">
            <header className="header">
              <div>
                <h1 className="header-title">Маппинг категорий</h1>
                <p className="header-subtitle">Настройка соответствия категорий между площадками</p>
              </div>
            </header>
            <div className="mapping-quick-start card">
              <h3>Настроить маппинг</h3>
              <p>Свяжите категории между маркетплейсами для автоматического переноса товаров</p>
              <Button onClick={() => setShowCategoryMapping(true)}>Открыть маппинг</Button>
            </div>
          </div>
        );

      case 'history':
        return (
          <div className="view-content">
            <header className="header">
              <div>
                <h1 className="header-title">История миграций</h1>
                <p className="header-subtitle">Журнал всех операций переноса</p>
              </div>
            </header>
            <div className="card empty-history">
              <div className="empty-state-icon">📜</div>
              <h3>История пуста</h3>
              <p>Здесь будут отображаться все выполненные миграции товаров</p>
              <p className="empty-state-hint">Функция будет доступна после добавления системы логирования</p>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="app-layout">
      <Sidebar
        currentView={currentView}
        setCurrentView={setCurrentView}
        onLogout={handleLogout}
        userRole="user"
      />

      <main className="main-content">
        {renderContent()}
      </main>

      {/* Модалки */}
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
        product={productToMigrate}
        onConfirm={handleConfirmMigrate}
        loading={isMigratingProductId === migrateProductId}
      />

      <BatchMigrateModal
        isOpen={showBatchModal}
        onClose={handleCloseBatchModal}
        selectedIds={selectedProductIds}
        products={products}
        onStartMigration={handleStartBatchMigration}
        pollProgress={pollBatchProgress}
        loading={productsLoading}
      />
    </div>
  );
}

export default App;