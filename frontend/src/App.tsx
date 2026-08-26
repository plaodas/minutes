import React, { useState } from 'react'
import Sidebar from './components/Sidebar'
import Dropzone from './components/Dropzone'
import ProcessingSteps from './components/ProcessingSteps'
import ResultCards from './components/ResultCards'
import UpdateToast from './components/UpdateToast'
import Toasts from './components/Toasts'

export default function App() {
  const [activeIndex, setActiveIndex] = useState<number>(-1)
  const [result, setResult] = useState<any | null>(null)

  return (
    <div className="min-h-screen bg-[var(--bg-default)] text-[var(--text-primary)]">
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-6">
          <div className="max-w-4xl mx-auto">
            <Dropzone setActiveIndex={setActiveIndex} setResult={setResult} />
            <div className="mt-6">
              <ProcessingSteps activeIndex={activeIndex >= 0 ? activeIndex : 0} />
            </div>
            <div className="mt-6">
              <ResultCards result={result} />
            </div>
          </div>
        </main>
      </div>
      <UpdateToast />
      <Toasts />
    </div>
  )
}
