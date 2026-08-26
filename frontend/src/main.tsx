import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/index.css'
import { registerServiceWorker } from './serviceWorkerRegistration'

const root = createRoot(document.getElementById('root')!)
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

// register SW for push notifications stub
registerServiceWorker()
