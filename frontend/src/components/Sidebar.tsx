import React from 'react'
import { Menu, Archive, Settings } from 'lucide-react'
import useLocalStorage from '../hooks/useLocalStorage'

const MenuItem: React.FC<{ icon: React.ReactNode; label: string }> = ({ icon, label }) => (
  <div className="flex items-center gap-3 p-3 rounded-md hover:bg-[var(--bg-surface)] cursor-pointer">
    <div className="w-6 h-6 text-[var(--accent)]">{icon}</div>
    <div className="text-sm">{label}</div>
  </div>
)

export default function Sidebar() {
  const [expanded, setExpanded] = useLocalStorage('sidebar-expanded', true)

  return (
    <aside
      className={`flex flex-col transition-all duration-200 bg-[var(--bg-surface)] p-3 ${
        expanded ? 'w-60' : 'w-16'
      }`}
      style={{ minHeight: '100vh' }}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="rounded-md w-8 h-8 bg-[var(--accent)]" />
          {expanded && <div className="font-semibold">Minutes</div>}
        </div>
        <button
          aria-label="toggle sidebar"
          onClick={() => setExpanded(!expanded)}
          className="p-1 rounded"
        >
          <Menu size={18} />
        </button>
      </div>

      <nav className="flex-1 space-y-2">
        <MenuItem icon={<Menu size={16} />} label="Upload" />
        <MenuItem icon={<Archive size={16} />} label="History" />
        <MenuItem icon={<Settings size={16} />} label="Settings" />
      </nav>

      <footer className="text-xs text-[var(--muted)] mt-4">v0.1 • Offline ready</footer>
    </aside>
  )
}
