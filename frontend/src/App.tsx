import React, { useState } from 'react'
import Sidebar, { NavigationView } from './components/Sidebar'
import Dropzone from './components/Dropzone'
import ProcessingSteps from './components/ProcessingSteps'
import ResultCards from './components/ResultCards'
import UpdateToast from './components/UpdateToast'
import Toasts from './components/Toasts'
import { HistoryView, SettingsView } from './components/WorkspaceViews'
import BucketsAdmin from './components/BucketsAdmin'
import { getUserFeatures } from './api/client'

export default function App() {
  const [activeIndex, setActiveIndex] = useState<number>(-1)
  const [result, setResult] = useState<any | null>(null)
  const [activeView, setActiveView] = useState<NavigationView>('upload')
  const [isAdmin, setIsAdmin] = useState(false)
  const [authChecked, setAuthChecked] = useState(false)
  const [authenticated, setAuthenticated] = useState<boolean | null>(null)

  React.useEffect(() => {
    let mounted = true
    const refresh = () => {
      getUserFeatures()
        .then((f) => {
          if (!mounted) return
          setIsAdmin(!!f && !!(f as any).is_admin)
          setAuthenticated(Boolean((f as any)?.authenticated))
          setAuthChecked(true)
        })
        .catch(() => {
          if (!mounted) return
          setIsAdmin(false)
          setAuthenticated(false)
          setAuthChecked(true)
        })
    }
    refresh()
    window.addEventListener('auth-changed', refresh)
    return () => {
      mounted = false
      window.removeEventListener('auth-changed', refresh)
    }
  }, [])

  if (authChecked && authenticated === false) {
    // show minimal login UI for unauthenticated users
    const LoginForm = React.lazy(() => import('./components/LoginForm'))
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg-default)]">
        <React.Suspense fallback={<div>Loading...</div>}>
          <div className="w-full max-w-md">
            <LoginForm />
          </div>
        </React.Suspense>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--bg-default)] text-[var(--text-primary)]">
      <div className="flex">
        <Sidebar activeView={activeView} onNavigate={setActiveView} showAdmin={isAdmin} />
        <main className="min-w-0 flex-1 px-4 pb-6 pt-20 sm:p-6 md:p-8">
          <div className="mx-auto max-w-4xl">
            {activeView === 'upload' && (
              <>
                <div className="mb-6">
                  <p className="text-sm font-medium text-[var(--accent)]">Audio workspace</p>
                  <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Create meeting minutes</h1>
                  <p className="mt-2 text-sm text-[var(--muted)]">Upload a recording to transcribe, summarize, and collect action items.</p>
                </div>
                <Dropzone setActiveIndex={setActiveIndex} setResult={setResult} />
                <div className="mt-6">
                  <ProcessingSteps activeIndex={activeIndex} />
                </div>
                <div className="mt-6">
                  <ResultCards result={result} />
                </div>
              </>
            )}
            {activeView === 'history' && <HistoryView onCreate={() => setActiveView('upload')} />}
            {activeView === 'settings' && <SettingsView />}
            {activeView === 'admin' && isAdmin && <BucketsAdmin />}
          </div>
        </main>
      </div>
      <UpdateToast />
      <Toasts />
    </div>
  )
}
