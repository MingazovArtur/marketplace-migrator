import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

function AppWithKey() {
  const token = localStorage.getItem('token');
  return <App key={token} />;
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AppWithKey />
  </StrictMode>,
)