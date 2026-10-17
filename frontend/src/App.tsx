import React, { useState } from 'react';

import Sidebar, { NavigationView } from './components/Sidebar';
import Dropzone from './components/Dropzone';
import ProcessingSteps from './components/ProcessingSteps';
import ResultCards from './components/ResultCards';
import UpdateToast from './components/UpdateToast';
import Toasts from './components/Toasts';
import HistoryView from './components/HistoryView';
import SettingsView from './components/SettingsView';
import BucketsAdmin from './components/BucketsAdmin';
import ServiceTokensAdmin from './components/ServiceTokensAdmin';
import AuditEventsAdmin from './components/AuditEventsAdmin';
import { getUserFeatures } from './api/client';
import { API_BASE, rememberHayamimiAvailability, showAdminControls } from './lib/apiConfig';
import { minutesTaskIdFromHash } from './lib/minutesLink';

export default function App() {
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const [result, setResult] = useState<unknown | null>(null);
  const [activeView, setActiveView] = useState<NavigationView>(() =>
    minutesTaskIdFromHash(window.location.hash) ? 'history' : 'upload'
  );
  const [isAdmin, setIsAdmin] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const adminNav = isAdmin && showAdminControls();

  React.useEffect(() => {
    let mounted = true;
    const refresh = () => {
      getUserFeatures()
        .then((f) => {
          if (!mounted) return;
          setIsAdmin(!!f.is_admin);
          setAuthenticated(Boolean(f.authenticated));
          setAuthChecked(true);
        })
        .catch(() => {
          if (!mounted) return;
          setIsAdmin(false);
          setAuthenticated(false);
          setAuthChecked(true);
        });
    };
    refresh();
    window.addEventListener('auth-changed', refresh);
    return () => {
      mounted = false;
      window.removeEventListener('auth-changed', refresh);
    };
  }, []);

  React.useEffect(() => {
    const openHistoryForMinutesLink = () => {
      if (minutesTaskIdFromHash(window.location.hash)) setActiveView('history');
    };
    window.addEventListener('hashchange', openHistoryForMinutesLink);
    return () => window.removeEventListener('hashchange', openHistoryForMinutesLink);
  }, []);

  React.useEffect(() => {
    let mounted = true;
    fetch(`${API_BASE}/health`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { hayamimi?: boolean } | null) => {
        if (mounted) rememberHayamimiAvailability(body?.hayamimi === true);
      })
      .catch(() => {
        if (mounted) rememberHayamimiAvailability(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (authChecked && authenticated === false) {
    // show minimal login UI for unauthenticated users
    const LoginForm = React.lazy(() => import('./components/LoginForm'));
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg-default)]">
        <React.Suspense fallback={<div>読み込み中…</div>}>
          <div className="w-full max-w-md">
            <LoginForm />
          </div>
        </React.Suspense>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg-default)] text-[var(--text-primary)]">
      <div className="flex">
        <Sidebar activeView={activeView} onNavigate={setActiveView} showAdmin={adminNav} />
        <main className="min-w-0 flex-1 px-4 pb-6 pt-20 sm:p-6 md:p-8">
          <div className="mx-auto max-w-4xl">
            {activeView === 'upload' && (
              <>
                <div className="mb-6">
                  <p className="text-sm font-medium text-[var(--accent)]">音声</p>
                  <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">議事録を作成</h1>
                  <p className="mt-2 text-sm text-[var(--muted)]">
                    録音をアップロードすると、文字起こし、要約、アクションアイテムを作ります。
                  </p>
                </div>
                <Dropzone setActiveIndex={setActiveIndex} setResult={setResult} />
                <div className="mt-6">
                  <ProcessingSteps activeIndex={activeIndex} />
                </div>
                <div className="mt-6">
                  <ResultCards result={result} onResultChange={setResult} />
                </div>
              </>
            )}
            {activeView === 'history' && <HistoryView onCreate={() => setActiveView('upload')} />}
            {activeView === 'settings' && <SettingsView />}
            {activeView === 'admin' && adminNav && (
              <>
                <BucketsAdmin />
                <div className="mt-8">
                  <ServiceTokensAdmin />
                </div>
                <div className="mt-8">
                  <AuditEventsAdmin />
                </div>
              </>
            )}
          </div>
        </main>
      </div>
      <UpdateToast />
      <Toasts />
    </div>
  );
}
