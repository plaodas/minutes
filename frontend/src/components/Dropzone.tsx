import React, { useCallback, useRef, useState } from 'react';
import { motion } from 'framer-motion';

import { uploadAudioBgWithProgress } from '../api/client';
import { useActiveTask } from '../hooks/useActiveTask';
import sanitizeError from '../lib/sanitizeError';

import ErrorModal from './ErrorModal';
import UploadProgress from './UploadProgress';

type Props = {
  setActiveIndex: (i: number) => void;
  setResult: (r: unknown | null) => void;
};

export default function Dropzone({ setActiveIndex, setResult }: Props) {
  const [dragActive, setDragActive] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [lastFile, setLastFile] = useState<File | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadErrorDetails, setUploadErrorDetails] = useState<string | null>(null);
  const [showErrorModal, setShowErrorModal] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const xhrRef = useRef<XMLHttpRequest | null>(null);
  const [running, setRunning] = useState(false);

  const {
    transcribeProgress,
    error: taskError,
    lastErrorDetails: taskErrorDetails,
    stopPolling,
  } = useActiveTask(running ? taskId : null, {
    onStageIndex: setActiveIndex,
    onResult: (result) => {
      setResult(result);
      setRunning(false);
    },
    onFailure: () => {
      setRunning(false);
    },
    onCancelled: () => {
      setRunning(false);
    },
  });

  const error = uploadError ?? taskError;
  const lastErrorDetails = uploadErrorDetails ?? taskErrorDetails;

  const abortUpload = useCallback(() => {
    if (!xhrRef.current) return;
    try {
      xhrRef.current.abort();
    } catch {
      // XHR may already be closed
    }
    xhrRef.current = null;
  }, []);

  const onDrop = useCallback(
    async (files: FileList | null) => {
      setUploadError(null);
      setUploadErrorDetails(null);
      if (!files || files.length === 0) return;
      const f = files[0];
      setLastFile(f);
      setFileName(f.name);

      abortUpload();
      stopPolling();
      setRunning(false);

      try {
        // ensure a user id exists in localStorage so uploads include X-User-Id
        try {
          const existing =
            localStorage.getItem('minutes.userId') || localStorage.getItem('user_id');
          if (!existing) {
            try {
              const id =
                (window as Window & { crypto?: Crypto }).crypto?.randomUUID?.() ||
                'id-' + Math.random().toString(36).slice(2, 10);
              localStorage.setItem('minutes.userId', id);
              try {
                window.dispatchEvent(
                  new CustomEvent('appToast', {
                    detail: { type: 'success', message: 'User ID generated and saved for uploads' },
                  })
                );
              } catch {
                // toast dispatch is best-effort
              }
            } catch {
              try {
                const id2 = 'id-' + Math.random().toString(36).slice(2, 10);
                localStorage.setItem('minutes.userId', id2);
                try {
                  window.dispatchEvent(
                    new CustomEvent('appToast', {
                      detail: {
                        type: 'success',
                        message: 'User ID generated and saved for uploads',
                      },
                    })
                  );
                } catch {
                  // toast dispatch is best-effort
                }
              } catch {
                // localStorage unavailable
              }
            }
          }
        } catch {
          // localStorage unavailable
        }

        setActiveIndex(0);
        setUploadProgress(0);
        const { xhr, promise } = uploadAudioBgWithProgress(f, (p) => setUploadProgress(p));
        xhrRef.current = xhr;
        const resp = await promise;
        const id = resp.task_id || resp.taskId || resp.id;
        if (!id) throw new Error('no task id returned');
        setTaskId(id);

        try {
          const raw = localStorage.getItem('recent_tasks');
          const arr = raw ? JSON.parse(raw) : [];
          arr.unshift({ id, name: f.name, created_at: new Date().toISOString() });
          localStorage.setItem('recent_tasks', JSON.stringify(arr.slice(0, 50)));
        } catch {
          // recent-task cache is optional
        }

        setUploadProgress(null);
        setRunning(true);
      } catch (e: unknown) {
        console.error(e);
        const msg = e instanceof Error ? e.message : String(e);
        setUploadError(msg);
        try {
          setUploadErrorDetails(sanitizeError(e));
        } catch {
          setUploadErrorDetails(msg);
        }
        setActiveIndex(-1);
        setUploadProgress(null);
        setRunning(false);
      }
    },
    [abortUpload, setActiveIndex, stopPolling]
  );

  const handleDrop: React.DragEventHandler = (e) => {
    e.preventDefault();
    setDragActive(false);
    onDrop(e.dataTransfer.files);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    onDrop(e.target.files);
  };

  const handleRetry = () => {
    if (!lastFile) return;
    const dt = new DataTransfer();
    dt.items.add(lastFile);
    onDrop(dt.files);
  };

  const cancelAll = useCallback(() => {
    abortUpload();
    stopPolling();
    setRunning(false);
    setUploadProgress(null);
    setTaskId(null);
    setActiveIndex(-1);
    window.dispatchEvent(
      new CustomEvent('appToast', { detail: { type: 'info', message: 'Upload cancelled' } })
    );
  }, [abortUpload, setActiveIndex, stopPolling]);

  return (
    <div>
      <label
        aria-label="Upload audio file"
        className={`block rounded-lg border border-transparent p-5 sm:p-8 glass-card cursor-pointer transition-shadow ${dragActive ? 'drag-active shadow-lg' : 'hover:shadow-md focus:shadow-md'}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <input type="file" accept="audio/*" className="hidden" onChange={handleFileInput} />
        <div className="flex flex-col items-center justify-center gap-4">
          <motion.div
            animate={{ scale: dragActive ? 1.03 : 1 }}
            transition={{ type: 'spring', stiffness: 200 }}
          >
            <div className="text-lg font-medium">Drop your audio file</div>
          </motion.div>
          <div className="text-sm text-[var(--muted)]">MP3 / WAV supported · max 200MB</div>
          <div className="mt-2 text-xs text-[var(--accent)]">Tap to select or drop a file</div>
          {dragActive && (
            <div className="w-full h-8 mt-4 bg-gradient-to-r from-accent/30 to-transparent rounded-md" />
          )}
          {fileName && (
            <div className="mt-2 max-w-full break-all text-sm text-[var(--muted)]">
              Selected: {fileName}
            </div>
          )}
          <UploadProgress uploadProgress={uploadProgress} transcribeProgress={transcribeProgress} />
          {running && (
            <div className="mt-3">
              <button className="px-3 py-1 rounded bg-gray-200" onClick={cancelAll}>
                Cancel
              </button>
            </div>
          )}
          {taskId && <div className="mt-2 max-w-full break-all text-sm">Task: {taskId}</div>}
          {error && (
            <div className="mt-2 flex items-center gap-3">
              <div className="text-sm text-red-600">Error: {error}</div>
              {lastFile && (
                <button
                  onClick={handleRetry}
                  className="ml-2 rounded bg-[var(--accent)] px-3 py-1 text-xs text-white"
                >
                  Retry
                </button>
              )}
              <button
                onClick={() => setShowErrorModal(true)}
                className="ml-2 rounded border border-slate-200 bg-white px-3 py-1 text-xs"
              >
                Details
              </button>
            </div>
          )}
          <ErrorModal
            open={showErrorModal}
            onClose={() => setShowErrorModal(false)}
            title="Server response"
            content={lastErrorDetails}
          />
        </div>
      </label>
    </div>
  );
}
