import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './index.css';
import App from './App.jsx';

/* Round 7: провайдеры данных и маршрутов.
 *
 * HashRouter (а не BrowserRouter): публичные страницы и так жили на хэш-URL
 * (#/privacy, #/help), а SPA отдаётся с «/» без catch-all на сервере —
 * с хэш-роутингом глубокие ссылки работают без настройки nginx/backend.
 *
 * QueryClient: единый кэш на всё приложение. refetchOnWindowFocus выключен —
 * обновления управляются инвалидацией после мутаций, а не фокусом окна. */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <App />
      </HashRouter>
    </QueryClientProvider>
  </StrictMode>
);
