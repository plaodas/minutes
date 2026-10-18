import React, { useEffect, useRef } from 'react';

import { useToast } from './ToastProvider';

function clipboardWrite(token: string): Promise<void> {
  const write = navigator.clipboard?.writeText;
  if (!write) return Promise.reject(new Error('no clipboard'));
  return Promise.race([
    write.call(navigator.clipboard, token),
    new Promise<void>((_, reject) => {
      window.setTimeout(() => reject(new Error('clipboard timeout')), 1000);
    }),
  ]);
}

function copyWithCommand(token: string) {
  const area = document.createElement('textarea');
  area.value = token;
  area.setAttribute('readonly', '');
  area.style.position = 'absolute';
  area.style.left = '-9999px';
  document.body.appendChild(area);
  area.select();
  const copied = document.execCommand('copy');
  document.body.removeChild(area);
  if (!copied) throw new Error('copy failed');
}

export default function CreatedServiceToken({
  token,
  onClose,
}: {
  token: string;
  onClose: () => void;
}) {
  const { addToast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [token]);

  const handleCopy = async () => {
    try {
      await clipboardWrite(token);
      addToast('トークンをクリップボードにコピーしました', { level: 'success' });
    } catch {
      try {
        copyWithCommand(token);
        addToast('トークンをクリップボードにコピーしました', { level: 'success' });
      } catch {
        addToast('コピーに失敗しました', { level: 'error' });
      }
    }
  };

  return (
    <div className="mb-4 rounded border border-[var(--accent)] p-3" role="status">
      <p className="mb-2 text-sm">
        このトークンは一度だけ表示されます。コピーして保管してください。
      </p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          ref={inputRef}
          readOnly
          aria-label="作成したサービストークン"
          value={token}
          onFocus={(event) => event.currentTarget.select()}
          className="min-w-0 flex-1 rounded border bg-white px-2 py-1 font-mono text-sm"
        />
        <button
          type="button"
          onClick={() => void handleCopy()}
          className="rounded bg-[var(--accent)] px-3 py-1 text-sm text-white"
        >
          コピー
        </button>
        <button type="button" onClick={onClose} className="rounded bg-slate-100 px-3 py-1 text-sm">
          閉じる
        </button>
      </div>
    </div>
  );
}
