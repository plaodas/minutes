import React from 'react'
import { motion } from 'framer-motion'

const steps = ['Uploading', 'preprocess', 'transcribing', 'formatting']

export default function ProcessingSteps({ activeIndex }: { activeIndex: number }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 lg:flex lg:items-center lg:gap-6" aria-label="Processing progress">
      {steps.map((s, i) => (
        <li key={s} className="flex min-w-0 items-center gap-3">
          <motion.div
            animate={{ scale: activeIndex === i ? 1.08 : 1 }}
            className={`h-4 w-4 shrink-0 rounded-full ${activeIndex === i ? 'bg-[var(--accent)]' : 'bg-gray-300'}`}
          />
          <span className={`truncate text-sm ${activeIndex === i ? 'font-medium' : 'text-[var(--muted)]'}`}>{s}</span>
        </li>
      ))}
    </ol>
  )
}
