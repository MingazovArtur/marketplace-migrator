import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import AnimatedCounter from '../common/AnimatedCounter';
import { PLATFORMS, getUnavailablePlatforms } from '../../utils/platformUtils';
import Icon from '../icons';

const BatchMigrateModal = ({ isOpen, onClose, selectedIds, products, onStartMigration, pollProgress, loading }) => {
  const [selectedPlatform, setSelectedPlatform] = useState('');
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState({ current: 0, total: 0, percent: 0, status: 'pending', success: 0, errors: 0 });
  const [completed, setCompleted] = useState(false);

  useEffect(() => {
    if (isOpen && selectedIds.length > 0) {
      const unavailable = getUnavailablePlatforms(products, selectedIds);
      const available = PLATFORMS.filter(p => !unavailable.includes(p));
      setSelectedPlatform(available[0]?.id || '');
      setTaskId(null);
      setCompleted(false);
      setProgress({ current: 0, total: selectedIds.length, percent: 0, status: 'pending', success: 0, errors: 0 });
    }
  }, [isOpen, selectedIds, products]);

  if (!isOpen || selectedIds.length === 0) return null;

  const unavailablePlatforms = getUnavailablePlatforms(products, selectedIds);
  const availablePlatforms = PLATFORMS.filter(p => !unavailablePlatforms.includes(p));

  const handleStart = async () => {
    if (!selectedPlatform) return;
    const data = await onStartMigration(selectedIds, selectedPlatform);
    if (data && data.task_id) {
      setTaskId(data.task_id);
      pollProgress(data.task_id, setProgress, (finalProgress) => {
        setProgress(finalProgress);
        setCompleted(true);
      });
    }
  };

  return (
    <div className="modal-overlay" onClick={() => !completed && onClose()}>
      <div className="modal modal-batch" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">🔄 Пакетная миграция</h2>
          {completed && <button type="button" className="close-btn" onClick={onClose} title="Закрыть"><Icon name="close" size={16} /></button>}
        </div>

        {!taskId ? (
          <>
            <p className="modal-text">
              Выбрано товаров: <b>{selectedIds.length}</b>. Выберите целевую платформу:
            </p>
            <div className="platform-selector">
              {availablePlatforms.map(p => (
                <button
                  key={p.id}
                  className={`platform-btn ${selectedPlatform === p.id ? 'platform-btn-active' : ''}`}
                  onClick={() => setSelectedPlatform(p.id)}
                  data-platform={p.id}
                >
                  <div className="platform-logo" style={{
                    backgroundColor: selectedPlatform === p.id ? p.color : 'var(--bg-tertiary)',
                    color: selectedPlatform === p.id ? 'white' : 'var(--text-muted)'
                  }}>
                    {p.logoText}
                  </div>
                  <span>{p.name}</span>
                </button>
              ))}
            </div>
            <div className="modal-hint-box">
              <span className="hint-icon">⚡</span>
              <p>Миграция будет выполняться в фоновом режиме. Вы сможете наблюдать за прогрессом в реальном времени.</p>
            </div>
            <div className="modal-actions">
              <Button variant="outline" onClick={onClose}>Отмена</Button>
              <Button onClick={handleStart} disabled={loading || !selectedPlatform}>
                🚀 Запустить миграцию
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="batch-progress-container">
              <div className="progress-stats">
                <div className="stat-item">
                  <div className="stat-label">Всего</div>
                  <div className="stat-value"><AnimatedCounter target={progress.total} duration={500} /></div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Обработано</div>
                  <div className="stat-value"><AnimatedCounter target={progress.current} duration={300} /></div>
                </div>
                <div className="stat-item success">
                  <div className="stat-label">Успешно</div>
                  <div className="stat-value"><AnimatedCounter target={progress.success || 0} duration={300} /></div>
                </div>
                <div className="stat-item error">
                  <div className="stat-label">Ошибок</div>
                  <div className="stat-value"><AnimatedCounter target={progress.errors || 0} duration={300} /></div>
                </div>
              </div>
              
              {/* Плавный прогресс-бар с shine-эффектом */}
              <div className="progress-bar-wrapper">
                <div 
                  className="progress-bar-fill" 
                  style={{ width: `${progress.percent || 0}%` }}
                />
                <div className="progress-bar-text">{Math.round(progress.percent || 0)}%</div>
              </div>
              
              <div className="progress-status">
                {progress.status === 'pending' && <span>⏳ Ожидание запуска...</span>}
                {progress.status === 'processing' && <span>⚙️ Обработка товаров...</span>}
                {progress.status === 'completed' && (
                  <span className="success-text">
                    ✅ Миграция завершена! Успешно: {progress.success}, Ошибок: {progress.errors}
                  </span>
                )}
                {progress.status === 'error' && <span className="error-text">❌ Произошла ошибка</span>}
              </div>
              
              {progress.error_details && progress.error_details.length > 0 && (
                <div className="error-details">
                  <h4>Детали ошибок:</h4>
                  <ul>{progress.error_details.map((err, i) => <li key={i}>Товар #{err.id}: {err.error}</li>)}</ul>
                </div>
              )}
            </div>
            {completed && (
              <div className="modal-actions">
                <Button onClick={onClose}>✅ Закрыть и обновить таблицу</Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default BatchMigrateModal;