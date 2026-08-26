import React from 'react'
import Sidebar from './components/Sidebar'
import Dropzone from './components/Dropzone'
import ProcessingSteps from './components/ProcessingSteps'
import ResultCards from './components/ResultCards'

export default function App() {
  return (
    <div className="min-h-screen bg-[var(--bg-default)] text-[var(--text-primary)]">
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-6">
          <div className="max-w-4xl mx-auto">
            <Dropzone />
            <div className="mt-6">
              <ProcessingSteps />
            </div>
            <div className="mt-6">
              <ResultCards />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
