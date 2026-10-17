import React from 'react';
import { Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';

const steps = [
  { id: 'uploading', label: 'アップロード' },
  { id: 'preprocess', label: '前処理' },
  { id: 'transcribing', label: '文字起こし' },
  { id: 'formatting', label: '整形' },
];

export default function ProcessingSteps({ activeIndex }: { activeIndex: number }) {
  const isRunning = activeIndex >= 0;
  const currentStep = isRunning ? steps[activeIndex]?.label : '音声を待っています';

  return (
    <>
      {/* Mobile: compact current status only */}
      <div className="sm:hidden">
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-3 rounded-md bg-white/60 p-3 cursor-default"
        >
          {isRunning ? (
            <Loader2 size={16} className="animate-spin text-[var(--accent)]" />
          ) : (
            <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
          )}
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{currentStep}</div>
            <div className="text-xs text-[var(--muted)]">
              {isRunning
                ? `${activeIndex + 1} / ${steps.length} 段階`
                : 'アップロードを待っています'}
            </div>
          </div>
        </div>
      </div>

      {/* Desktop / tablet: full timeline */}
      <div className="hidden sm:block">
        <section className="border-l-2 border-slate-200 pl-4" aria-label="処理状況">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">処理状況</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">{currentStep}</p>
            </div>
            {isRunning && (
              <span className="shrink-0 text-xs font-medium text-[var(--accent)]">
                {activeIndex + 1} / {steps.length} 段階
              </span>
            )}
          </div>
          <ol className="grid gap-3 sm:grid-cols-2 lg:flex lg:items-center lg:gap-6">
            {steps.map((step, index) => {
              const isCurrent = activeIndex === index;
              const isComplete = activeIndex > index;
              return (
                <li key={step.id} className="flex min-w-0 items-center gap-2">
                  {isCurrent ? (
                    <motion.span
                      animate={{ rotate: 360 }}
                      transition={{ repeat: Infinity, duration: 1.4, ease: 'linear' }}
                      className="shrink-0 text-[var(--accent)]"
                    >
                      <Loader2 size={17} />
                    </motion.span>
                  ) : (
                    <span
                      className={`h-2.5 w-2.5 shrink-0 rounded-full ${isComplete ? 'bg-[var(--accent)]' : 'bg-slate-300'}`}
                    />
                  )}
                  <span
                    className={`truncate text-sm ${isCurrent || isComplete ? 'font-medium text-[var(--text-primary)]' : 'text-[var(--muted)]'}`}
                  >
                    {step.label}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      </div>
    </>
  );
}
