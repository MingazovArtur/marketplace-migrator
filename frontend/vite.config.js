import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // ✅ Разрешаем внешние подключения
    port: 5173,
    // ✅ Проксируем на имя Docker-сервиса 'backend', а не на localhost
    proxy: {
      '/api': {
        target: 'http://backend:8000',  // ← ИЗМЕНИТЬ ЗДЕСЬ
        changeOrigin: true,
      },
      // Фото: отдаёт backend с авторизацией по куке (routers/media.py)
      '/media': {
        target: 'http://backend:8000',
        changeOrigin: true,
      }
    }
  }
})
