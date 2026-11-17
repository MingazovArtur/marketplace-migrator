import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Дев-сервер слушает все интерфейсы: так фронт-контейнер доступен и с
    // хоста, и из LAN (например, проверка вёрстки с телефона). DEV-ONLY
    // компромисс — модель доверия:
    //   vite сам проксирует /api и /media на backend (см. proxy ниже), и для
    //   API все такие запросы приходят «с IP контейнера фронта»: LAN-клиенты
    //   для backend не различаются (get_client_ip видит адрес фронта),
    //   баны/лимиты по IP в dev-сети фактически не работают. Это осознанно:
    //   dev-сеть считается доверенной. Прод-фронт — статика за nginx, он же
    //   проксирует /api и проставляет X-Real-IP (deploy/nginx), инвариант
    //   «порт 8000 не должен торчать наружу» не нарушается.
    host: '0.0.0.0',
    port: 5173,
    // Проксируем на имя Docker-сервиса 'backend' (в dev-сети), не на localhost
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      // Фото: отдаёт backend с авторизацией по куке (routers/media.py)
      '/media': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
