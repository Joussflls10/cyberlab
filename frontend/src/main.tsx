import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

async function cleanupDevServiceWorkers() {
  if (!('serviceWorker' in navigator)) return

  try {
    const registrations = await navigator.serviceWorker.getRegistrations()
    await Promise.all(registrations.map((registration) => registration.unregister()))
  } catch (error) {
    console.warn('Failed to unregister service workers in dev:', error)
  }

  if (!('caches' in window)) return
  try {
    const cacheKeys = await caches.keys()
    await Promise.all(
      cacheKeys
        .filter((key) => key.startsWith('cyberlab-shell-'))
        .map((key) => caches.delete(key))
    )
  } catch (error) {
    console.warn('Failed to clear dev caches:', error)
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

if (import.meta.env.DEV) {
  cleanupDevServiceWorkers()
}

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((error) => {
      console.error('Service worker registration failed:', error)
    })
  })
}
