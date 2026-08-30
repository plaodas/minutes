import React from 'react'
import { Archive, ChevronLeft, ChevronRight, Menu, Settings, Upload, X } from 'lucide-react'
import useLocalStorage from '../hooks/useLocalStorage'

export type NavigationView = 'upload' | 'history' | 'settings'

type Props = {
  activeView: NavigationView
  onNavigate: (view: NavigationView) => void
}

const items: Array<{ view: NavigationView; label: string; icon: React.ReactNode }> = [
  { view: 'upload', label: 'Upload', icon: <Upload size={18} /> },
  { view: 'history', label: 'History', icon: <Archive size={18} /> },
  { view: 'settings', label: 'Settings', icon: <Settings size={18} /> },
]

export default function Sidebar({ activeView, onNavigate }: Props) {
  const [expanded, setExpanded] = useLocalStorage('sidebar-expanded', true)
  const [mobileOpen, setMobileOpen] = React.useState(false)

  const navigate = (view: NavigationView) => {
    onNavigate(view)
    setMobileOpen(false)
  }

  const navigation = (showLabels: boolean) => (
    <nav className="flex-1 space-y-1" aria-label="Main navigation">
      {items.map((item) => {
        const isActive = activeView === item.view
        return (
          <button
            key={item.view}
            type="button"
            aria-label={item.label}
            title={!showLabels ? item.label : undefined}
            onClick={() => navigate(item.view)}
            className={`flex w-full items-center rounded-md p-3 text-left transition-colors ${
              isActive ? 'bg-teal-50 text-[var(--accent)]' : 'hover:bg-[var(--bg-default)]'
            } ${showLabels ? 'gap-3' : 'justify-center'}`}
          >
            <span className="shrink-0">{item.icon}</span>
            {showLabels && <span className="text-sm font-medium">{item.label}</span>}
          </button>
        )
      })}
    </nav>
  )

  return (
    <>
      <button
        type="button"
        aria-label="Open menu"
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen(true)}
        className="fixed left-4 top-4 z-30 rounded-md bg-white p-2 shadow-sm ring-1 ring-black/5 md:hidden"
      >
        <Menu size={20} />
      </button>

      {mobileOpen && <button type="button" aria-label="Close menu" className="fixed inset-0 z-30 bg-slate-950/20 md:hidden" onClick={() => setMobileOpen(false)} />}

      <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-white p-3 shadow-xl transition-transform duration-200 md:hidden ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
          <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <img src="/images/minutes-logo.svg" alt="Minutes" className="h-8 w-8 shrink-0 object-contain" />
            <div className="font-semibold">Minutes</div>
          </div>
          <button type="button" aria-label="Close menu" onClick={() => setMobileOpen(false)} className="rounded p-1 hover:bg-[var(--bg-default)]"><X size={20} /></button>
        </div>
        {navigation(true)}
        <footer className="mt-4 text-xs text-[var(--muted)]">v0.1 · Offline ready</footer>
      </aside>

      <aside className={`hidden min-h-screen shrink-0 flex-col bg-white p-3 transition-all duration-200 md:flex ${expanded ? 'w-60' : 'w-16'}`}>
        <div className={`mb-5 flex items-center ${expanded ? 'justify-between' : 'justify-center'}`}>
          <div className="flex items-center gap-2">
            <img src="/images/minutes-logo.svg" alt="Minutes" className="h-8 w-8 shrink-0 object-contain" />
            {expanded && <div className="font-semibold">Minutes</div>}
          </div>
          <button
            type="button"
            aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
            title={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
            onClick={() => setExpanded(!expanded)}
            className={`rounded p-1 hover:bg-[var(--bg-default)] ${expanded ? '' : 'absolute left-20 top-5'}`}
          >
            {expanded ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
          </button>
        </div>
        {navigation(expanded)}
        {expanded && <footer className="mt-4 text-xs text-[var(--muted)]">v0.1 · Offline ready</footer>}
      </aside>
    </>
  )
}
