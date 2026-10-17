import React, { useEffect, useRef, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';

import useLocalStorage from '../hooks/useLocalStorage';
import { API_BASE, isJapaneseLanguage, rememberHayamimiAvailability } from '../lib/apiConfig';

import MyServiceTokens from './MyServiceTokens';
import { useToast } from './ToastProvider';

const LANGUAGE_LABELS: Record<string, string> = {
  Japanese: '日本語',
  English: '英語',
  'Auto-detect': '自動検出',
};

function languageLabel(value: string): string {
  return LANGUAGE_LABELS[value] ?? value;
}

export function SettingsView() {
  const [settings, setSettings] = useLocalStorage('minutes.settings', {
    language: 'Japanese',
    includeActions: true,
    engine: 'whisper',
  });
  const [hayamimiAvailable, setHayamimiAvailable] = useState<boolean | null>(null);
  const prevRef = useRef<typeof settings | null>(null);
  const { addToast } = useToast();
  const showEngine = hayamimiAvailable === true && isJapaneseLanguage(settings.language);

  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/health`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { hayamimi?: boolean } | null) => {
        if (cancelled) return;
        const available = body?.hayamimi === true;
        rememberHayamimiAvailability(available);
        setHayamimiAvailable(available);
      })
      .catch(() => {
        if (cancelled) return;
        rememberHayamimiAvailability(false);
        setHayamimiAvailable(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (hayamimiAvailable === false && settingsRef.current.engine === 'hayamimi') {
      setSettings({ ...settingsRef.current, engine: 'whisper' });
    }
  }, [hayamimiAvailable, setSettings]);

  useEffect(() => {
    if (prevRef.current === null) {
      prevRef.current = settings;
      return;
    }
    const prev = prevRef.current;
    prevRef.current = settings;
    if (prev.language !== settings.language) {
      addToast(`文字起こし言語: ${languageLabel(settings.language)}`, {
        level: 'success',
        duration: 2000,
      });
    }
    if (prev.includeActions !== settings.includeActions) {
      addToast(`アクションアイテムを含める: ${settings.includeActions ? 'オン' : 'オフ'}`, {
        level: 'success',
        duration: 2000,
      });
    }
    if (prev.engine !== settings.engine) {
      addToast(`文字起こしエンジン: ${settings.engine === 'hayamimi' ? '早耳' : 'Whisper'}`, {
        level: 'success',
        duration: 2000,
      });
    }
  }, [addToast, settings]);

  return (
    <section>
      <div className="mb-7">
        <p className="text-sm font-medium text-[var(--accent)]">設定</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">設定</h1>
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="flex items-start gap-3 border-b border-slate-100 p-4">
          <span className="rounded-md bg-teal-50 p-2 text-[var(--accent)]">
            <SlidersHorizontal size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <label htmlFor="language" className="block text-sm font-medium">
              文字起こし言語
            </label>
            <select
              id="language"
              value={settings.language}
              onChange={(event) => setSettings({ ...settings, language: event.target.value })}
              className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm sm:max-w-xs"
            >
              <option value="Japanese">日本語</option>
              <option value="English">英語</option>
              <option value="Auto-detect">自動検出</option>
            </select>
          </div>
        </div>
        {showEngine && (
          <div className="border-b border-slate-100 p-4 pl-[3.75rem]">
            <label htmlFor="engine" className="block text-sm font-medium">
              日本語の文字起こしエンジン
            </label>
            <select
              id="engine"
              value={settings.engine === 'hayamimi' ? 'hayamimi' : 'whisper'}
              onChange={(event) => setSettings({ ...settings, engine: event.target.value })}
              className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm sm:max-w-xs"
            >
              <option value="whisper">Whisper</option>
              <option value="hayamimi">早耳</option>
            </select>
          </div>
        )}
        <label
          aria-label="アクションアイテムを含める"
          className="flex cursor-pointer items-center justify-between gap-5 p-4"
        >
          <span>
            <span className="block text-sm font-medium">アクションアイテムを含める</span>
            <span className="mt-1 block text-sm text-[var(--muted)]">
              会議からタスクと担当を抽出します。
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
      <p className="mt-3 text-xs text-[var(--muted)]">設定はこのブラウザに保存されます。</p>
      <MyServiceTokens />
    </section>
  );
}

export default SettingsView;
