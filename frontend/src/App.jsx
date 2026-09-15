import React, { useState, useEffect, useCallback } from 'react'; // ✅ 1. Добавлен useEffect в импорт
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
import { api } from './api';
import './App.css';

function App() {
  const { token, isAuthenticated, handleLogin, handleLogout } = useAuth();
  const { loading: apiLoading } = useApi();
  const [message, setMessage] = useState('');
  
  // Состояния модалок
  const [showImportModal, setShowImportModal] = useState(false);
  const [showCategoryMapping, setShowCategoryMapping] = useState(false);
  const [migrateProductId, setMigrateProductId] = useState(null);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [selectedProductIds, setSelectedProductIds] = useState([]);

  // ✅ Слушатель для сброса выделения (оставляем как вы просили)
  useEffect(() => {
    const handleClearSelection = () => {
      setSelectedProductIds([]);
    };
    window.addEventListener('clearSelection', handleClearSelection);
    return () => window.removeEventListener('clearSelection', handleClearSelection);
  }, []);

  const {
    products,
    stats,
    loading: productsLoading,
    loadData,
    availableForBatch,
    getProductById
  } = useProducts(handleLogout);

  const {
    isMigratingProductId,
    migrateProduct,
    migrateBatch,
    pollBatchProgress
  } = useMigration(loadData, setMessage);

  // --- Обработчики ---

  const handleImport = useCallback(async (fullKey) => {
    try {
      const data = await api.importProducts(fullKey);
      if (data.success) {
        setMessage(`✅ Импортировано ${data.imported} товаров с ${data.platform_name}${data.is_mock ? ' (тест)' : ''}`);
        setShowImportModal(false);
        loadData();
      } else {
        setMessage('❌ Ошибка импорта: ' + (data.detail || 'неизвестно'));
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

    const unavailable = getUnavailablePlatforms(products, selectedProductIds);
    const unavailableIds = unavailable.map(p => p.id); 
    const availablePlatforms = PLATFORMS.filter(p => !unavailableIds.includes(p.id));

    if (availablePlatforms.length === 0) {
      setMessage('⚠️ Для выбранных товаров нет общих доступных платформ.');
      return; 
    }

    setShowBatchModal(true);
  }, [selectedProductIds, products]);

  // ✅ 2. Переименовали в handleCloseBatchModal, чтобы совпадало с пропсом в JSX
  const handleCloseBatchModal = useCallback(() => {
    setShowBatchModal(false);
    setSelectedProductIds([]); // ✅ ГАРАНТИРОВАННО очищаем выделение при закрытии
    loadData();
  }, [loadData]);

  // ✅ 3. УДАЛЕНЫ сломанные функции startBatchMigration и pollProgress. 
  // Вся логика прогресса теперь корректно работает через хук useMigration (pollBatchProgress).

  const handleStartBatchMigration = useCallback(async (ids, platform) => {
    try {
      const result = await migrateBatch(ids, platform);
      return result;
    } catch (err) {
      setMessage('❌ ' + (err.message || 'Ошибка запуска пакетной миграции'));
      setShowBatchModal(false);
      setSelectedProductIds([]); // ✅ Сбрасываем выделение при ошибке
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
      setMessage('✅ Отчет успешно скачан!');
    } catch (error) {
      setMessage('❌ Ошибка при скачивании отчета: ' + error.message);
    }
  }, [stats.total]);

  // --- Условный рендеринг ---

  if (!isAuthenticated) {
    return <Auth onLogin={handleLogin} />;
  }

  if (showCategoryMapping) {
    return <CategoryMapping onBack={() => setShowCategoryMapping(false)} />;
  }

  const productToMigrate = getProductById(migrateProductId);

  return (
    <div className="app-container">
      <header className="header">
        <div>
          <h1>🔄 Marketplace Migrator <span style={{ fontSize: '0.5em', color: '#10b981' }}>v4.0</span></h1>
          <p>Универсальный перенос карточек: Ozon, Wildberries, Яндекс Маркет</p>
        </div>
        <Button variant="outline" onClick={handleLogout} size="sm">🚪 Выйти</Button>
      </header>

      <Alert message={message} onClose={() => setMessage('')} />
      <StatsGrid stats={stats} />

      <div className="actions-panel">
        <Button onClick={() => setShowImportModal(true)}>📥 Импортировать товары</Button>
        <Button variant="secondary" onClick={() => setShowCategoryMapping(true)}>🗺️ Настройка маппинга</Button>
        <Button variant="secondary" onClick={handleOpenBatchModal} disabled={selectedProductIds.length === 0 || productsLoading}>
          🔄 Перенести выбранные ({selectedProductIds.length})
        </Button>
        <Button variant="secondary" onClick={handleExport} disabled={stats.total === 0}>📊 Скачать отчет (Excel)</Button>
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
        onClose={handleCloseBatchModal} // ✅ Теперь имя функции совпадает с объявлением
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