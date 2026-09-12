import React from 'react';
import { ChevronRight, Clock3, FileAudio } from 'lucide-react';

import type { HistoryItem } from '../lib/taskState';

type Props = {
  items: HistoryItem[];
  onOpenMinutes: (id: string) => void;
  onOpenEvents: (id: string) => void;
  sentinelRef?: React.Ref<HTMLDivElement>;
};

export default function HistoryList({ items, onOpenMinutes, onOpenEvents, sentinelRef }: Props) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      {items.length === 0 && (
        <div className="p-6 text-sm text-[var(--muted)]">
          No recent tasks. Upload audio to see history here.
        </div>
      )}

      {items.map((item) => (
        <div
          key={item.id}
          data-testid={`view-minutes-${item.id}`}
          role="button"
          tabIndex={0}
          aria-labelledby={`history-title-${item.id}`}
          aria-describedby={`history-desc-${item.id}`}
          onClick={() => onOpenMinutes(item.id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onOpenMinutes(item.id);
            }
          }}
          className="cursor-pointer flex w-full items-center gap-3 border-b border-slate-100 p-4 text-left last:border-0 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[var(--accent)] focus-visible:shadow-lg focus-visible:bg-slate-50 transform transition-transform transition-opacity duration-150 ease-out focus-visible:scale-105 focus-visible:-translate-y-1 focus-visible:opacity-100"
        >
          <span className="rounded-md bg-teal-50 p-2 text-[var(--accent)]">
            <FileAudio size={20} />
          </span>
          <span className="min-w-0 flex-1">
            <span id={`history-title-${item.id}`} className="block truncate text-sm font-medium">
              {item.name}
            </span>
            <span id={`history-desc-${item.id}`} className="sr-only">
              {item.created_at ? new Date(item.created_at).toLocaleString() + ', ' : ''}
              {item.status || 'Status unknown'}
            </span>
            <span className="mt-1 flex items-center gap-1 text-xs text-[var(--muted)]">
              <Clock3 size={13} />{' '}
              {item.created_at ? new Date(item.created_at).toLocaleString() : ''}
            </span>

            {typeof item.progress === 'number' && item.progress >= 0 && item.progress < 100 && (
              <div className="mt-2 w-full">
                <div className="relative h-2 w-full overflow-hidden rounded bg-slate-100">
                  <div
                    style={{ width: `${Math.max(0, Math.min(100, item.progress))}%` }}
                    className="absolute left-0 top-0 h-2 bg-[var(--accent)]"
                  />
                </div>
                <div className="mt-1 text-xs text-[var(--muted)]">
                  {Math.round(item.progress)}% — {item.status || 'processing'}
                </div>
              </div>
            )}

            <div className="mt-1 text-xs text-[var(--muted)]">
              {item.histories && item.histories.length > 0 ? (
                item.histories.slice(0, 3).map((h, idx) => (
                  <div key={idx} className="truncate">
                    {h.event_ts ? new Date(h.event_ts).toLocaleString() + ' — ' : ''}
                    <strong>{h.event_type}</strong>
                    {h.payload?.error ? ` — ${h.payload.error}` : ''}
                  </div>
                ))
              ) : (
                <div>—</div>
              )}
              <div className="mt-2 flex items-center gap-2">
                <button
                  data-testid={`view-history-${item.id}`}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenEvents(item.id);
                  }}
                  className="text-xs text-[var(--accent)]"
                >
                  View full events
                </button>
                <span className="text-xs text-[var(--muted)]">
                  Showing {item.histories ? item.histories.length : 0}
                  {item.event_count ? ` of ${item.event_count}` : ''}
                </span>
              </div>
            </div>
          </span>

          <span className="hidden rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 sm:inline">
            {item.latest ? item.latest.event_type : '—'}
          </span>
          <button
            aria-label={`View minutes for ${item.name || item.id}`}
            onClick={(e) => {
              e.stopPropagation();
              onOpenMinutes(item.id);
            }}
            className="shrink-0 text-slate-400 rounded hover:bg-slate-100 p-1"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      ))}
      <div aria-hidden="true" data-testid="history-list-sentinel" ref={sentinelRef} />
    </div>
  );
}
