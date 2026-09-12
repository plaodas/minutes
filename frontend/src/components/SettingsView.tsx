import React, { useEffect, useRef } from 'react';
import { SlidersHorizontal } from 'lucide-react';

import useLocalStorage from '../hooks/useLocalStorage';

import { useToast } from './ToastProvider';

export function SettingsView() {
  const [settings, setSettings] = useLocalStorage('minutes.settings', {
    language: 'Japanese',
    includeActions: true,
  });
  const prevRef = useRef<typeof settings | null>(null);
  const { addToast } = useToast();

  useEffect(() => {
    if (prevRef.current === null) {
      prevRef.current = settings;
      return;
    }
    const prev = prevRef.current;
    prevRef.current = settings;
    if (prev.language !== settings.language) {
      addToast(`Transcript language: ${settings.language}`, { level: 'success', duration: 2000 });
    }
    if (prev.includeActions !== settings.includeActions) {
      addToast(`Include action items: ${settings.includeActions ? 'On' : 'Off'}`, {
        level: 'success',
        duration: 2000,
      });
    }
  }, [addToast, settings]);

  return (
    <section>
      <div className="mb-7">
        <p className="text-sm font-medium text-[var(--accent)]">Preferences</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Settings</h1>
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="flex items-start gap-3 border-b border-slate-100 p-4">
          <span className="rounded-md bg-teal-50 p-2 text-[var(--accent)]">
            <SlidersHorizontal size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <label htmlFor="language" className="block text-sm font-medium">
              Transcript language
            </label>
            <select
              id="language"
              value={settings.language}
              onChange={(event) => setSettings({ ...settings, language: event.target.value })}
              className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm sm:max-w-xs"
            >
              <option>Japanese</option>
              <option>English</option>
              <option>Auto-detect</option>
            </select>
          </div>
        </div>
        <label
          aria-label="Include action items"
          className="flex cursor-pointer items-center justify-between gap-5 p-4"
        >
          <span>
            <span className="block text-sm font-medium">Include action items</span>
            <span className="mt-1 block text-sm text-[var(--muted)]">
              Extract tasks and owners from the meeting.
            </span>
          </span>
          <input
            type="checkbox"
            checked={!!settings.includeActions}
            onChange={(event) => setSettings({ ...settings, includeActions: event.target.checked })}
            className="h-5 w-5 shrink-0 accent-[var(--accent)]"
          />
        </label>
      </div>
      <p className="mt-3 text-xs text-[var(--muted)]">
        Settings are saved locally to your browser.
      </p>
    </section>
  );
}

export default SettingsView;
