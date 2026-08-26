import React from 'react'
import { motion } from 'framer-motion'

const steps = ['Uploading', 'preprocess', 'transcribing', 'formatting']

export default function ProcessingSteps({ activeIndex }: { activeIndex: number }) {
  return (
    <div className="flex items-center gap-6">
      {steps.map((s, i) => (
        <div key={s} className="flex items-center gap-3">
          <motion.div
            animate={{ scale: activeIndex === i ? 1.08 : 1 }}
            className={`w-4 h-4 rounded-full ${activeIndex === i ? 'bg-[var(--accent)]' : 'bg-gray-300'}`}
          />
          <div className={`text-sm ${activeIndex === i ? 'font-medium' : 'text-[var(--muted)]'}`}>{s}</div>
        </div>
      ))}
    </div>
  )
}
