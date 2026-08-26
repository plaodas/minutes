import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

const pwaOptions = {
  registerType: 'autoUpdate',
  devOptions: {
    enabled: false
  },
  manifest: {
    name: 'Minutes',
    short_name: 'Minutes',
    start_url: '/',
    display: 'standalone',
    background_color: '#f7f7f9',
    theme_color: '#0ea5a1',
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' }
    ]
  },
  workbox: {
    runtimeCaching: [
      {
        urlPattern: /\/api\/.*$/,
        // Avoid caching API calls in the service worker to prevent
        // the SW from intercepting multipart uploads or producing
        // unexpected network errors. Use NetworkOnly so requests
        // are always forwarded to the network/backend.
        handler: 'NetworkOnly',
        options: { cacheName: 'api-cache' }
      },
      {
        urlPattern: /\.(?:js|css|png|jpg|jpeg|svg)$/,
        handler: 'CacheFirst',
        options: { cacheName: 'assets-cache' }
      }
    ]
  }
}

export default defineConfig({
  plugins: [react(), VitePWA(pwaOptions)],
  server: {
    port: 5173
  }
})
