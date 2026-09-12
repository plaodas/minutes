import React, { useCallback, useRef, useState, useEffect } from 'react';
import { motion } from 'framer-motion';

import sanitizeError from '../lib/sanitizeError';
import { taskStageFromStatus, taskStageToIndex } from '../lib/taskEvents';
import { useTaskEvents } from '../events/TaskEventsProvider';
import { uploadAudioBgWithProgress, getBgStatus, getBgResult } from '../api/client';

import ErrorModal from './ErrorModal';

type Props = {
  setActiveIndex: (i: number) => void;
  setResult: (r: any | null) => void;
};

export default function Dropzone({ setActiveIndex, setResult }: Props) {
  const [dragActive, setDragActive] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [lastFile, setLastFile] = useState<File | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastErrorDetails, setLastErrorDetails] = useState<string | null>(null);
  const [showErrorModal, setShowErrorModal] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const xhrRef = useRef<XMLHttpRequest | null>(null);
  const pollRef = useRef<number | null>(0);
  const [running, setRunning] = useState(false);
  const [transcribeProgress, setTranscribeProgress] = useState<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = 0;
    }
  }, []);

  const completeTask = useCallback(
    async (id: string, eventResult?: unknown) => {
      const response = eventResult === undefined ? await getBgResult(id) : eventResult;
      const result =
        eventResult === undefined &&
        response &&
        typeof response === 'object' &&
        'result' in response
          ? response.result
          : response;
      const structured =
        result && typeof result === 'object' && !Array.isArray(result)
          ? { ...result, task_id: 'task_id' in result ? result.task_id : id }
          : result;
      stopPolling();
      setResult(structured);
      setActiveIndex(4);
      setTranscribeProgress(null);
      setRunning(false);
    },
    [setActiveIndex, setResult, stopPolling]
  );

  const eventConnectionState = useTaskEvents(
    (event) => {
      if (event.event_type === 'progress') {
        setTranscribeProgress(Math.round(event.payload.progress));
      }
      if (event.event_type === 'status') {
        const stage = event.stage ?? taskStageFromStatus(event.payload.status);
        const idx = taskStageToIndex(stage);
        setActiveIndex(idx);
        if (idx >= 3) {
          setTranscribeProgress(null);
        }
        if (idx >= 4 && taskId) {
          void completeTask(taskId);
        }
      }
      if (event.event_type === 'success' && taskId) {
        void completeTask(taskId, event.payload.result);
      }
      if (event.event_type === 'failure') {
        const message = event.payload.error || 'Task failed';
        stopPolling();
        setError(message);
        setLastErrorDetails(sanitizeError(message));
        setActiveIndex(-1);
        setTranscribeProgress(null);
        setRunning(false);
        window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'error', message } }));
      }
      if (event.event_type === 'cancelled') {
        stopPolling();
        setActiveIndex(-1);
        setTranscribeProgress(null);
        setRunning(false);
      }
    },
    running ? taskId : null
  );

  const pollTaskStatus = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const statusResponse = await getBgStatus(id);
        const status = statusResponse.status || '';
        const backendError = statusResponse.error;

        if (backendError || statusResponse.stage === 'failed') {
          const message = backendError ? String(backendError) : 'Task failed';
          setError(message);
          setLastErrorDetails(sanitizeError(backendError || message));
          setActiveIndex(-1);
          window.dispatchEvent(new CustomEvent('appToast', { detail: { type: 'error', message } }));
          setRunning(false);
          return true;
        }

        const index = taskStageToIndex(statusResponse.stage ?? taskStageFromStatus(status));
        setActiveIndex(index);
        if (index >= 4) {
          await completeTask(id);
          return true;
        }
        return false;
      } catch (pollError) {
        console.warn('poll error', pollError);
        const detail = pollError instanceof Error ? pollError.message : String(pollError);
        setError(detail);
        setLastErrorDetails(sanitizeError(pollError));
        setRunning(false);
        return true;
      }
    },
    [completeTask, setActiveIndex]
  );

  useEffect(() => {
    stopPolling();
    if (
      !running ||
      !taskId ||
      eventConnectionState === 'open' ||
      eventConnectionState === 'connecting'
    ) {
      return;
    }

    let cancelled = false;
    const poll = async () => {
      const terminal = await pollTaskStatus(taskId);
      if (!cancelled && !terminal) {
        pollRef.current = window.setTimeout(poll, 10000);
      }
    };
    pollRef.current = window.setTimeout(poll, 1500);

    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [eventConnectionState, pollTaskStatus, running, stopPolling, taskId]);

  const onDrop = useCallback(
    async (files: FileList | null) => {
      setError(null);
      if (!files || files.length === 0) return;
      const f = files[0];
      setLastFile(f);
      setFileName(f.name);
      setTranscribeProgress(null);

      // abort any previous operations
      if (xhrRef.current) {
        try {
          xhrRef.current.abort();
        } catch {}
        xhrRef.current = null;
      }
      stopPolling();

      try {
        // ensure a user id exists in localStorage so uploads include X-User-Id
        try {
          const existing =
            localStorage.getItem('minutes.userId') || localStorage.getItem('user_id');
          if (!existing) {
            try {
              const id =
                (window as any).crypto?.randomUUID?.() ||
                'id-' + Math.random().toString(36).slice(2, 10);
              localStorage.setItem('minutes.userId', id);
              try {
                window.dispatchEvent(
                  new CustomEvent('appToast', {
                    detail: { type: 'success', message: 'User ID generated and saved for uploads' },
                  })
                );
              } catch {}
            } catch (e) {
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
                } catch {}
              } catch {}
            }
          }
        } catch {}

        setActiveIndex(0);
        setUploadProgress(0);
        const { xhr, promise } = uploadAudioBgWithProgress(f, (p) => setUploadProgress(p));
        xhrRef.current = xhr;
        const resp = await promise;
        const id = resp.task_id || resp.taskId || resp.id;
        if (!id) throw new Error('no task id returned');
        setTaskId(id);

        // persist recent task id for History view
        try {
          const raw = localStorage.getItem('recent_tasks');
          const arr = raw ? JSON.parse(raw) : [];
          arr.unshift({ id, name: f.name, created_at: new Date().toISOString() });
          // keep up to 50 entries
          const trimmed = arr.slice(0, 50);
          localStorage.setItem('recent_tasks', JSON.stringify(trimmed));
        } catch {
          // ignore
        }

        // clear upload UI
        setUploadProgress(null);
        setRunning(true);
      } catch (e: any) {
        console.error(e);
        const msg = String(e?.message || e);
        setError(msg);
        try {
          setLastErrorDetails(sanitizeError(e));
        } catch {
          setLastErrorDetails(msg);
        }
        setActiveIndex(-1);
        setUploadProgress(null);
        setRunning(false);
      }
    },
    [setActiveIndex, stopPolling]
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
    if (xhrRef.current) {
      try {
        xhrRef.current.abort();
      } catch {}
      xhrRef.current = null;
    }
    stopPolling();
    setRunning(false);
    setUploadProgress(null);
    setTaskId(null);
    setActiveIndex(-1);
    window.dispatchEvent(
      new CustomEvent('appToast', { detail: { type: 'info', message: 'Upload cancelled' } })
    );
  }, [setActiveIndex, stopPolling]);

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
          {uploadProgress !== null && (
            <div className="w-full mt-3">
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-[var(--accent)] h-2 rounded-full"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <div className="text-xs text-[var(--muted)] mt-1">Uploading: {uploadProgress}%</div>
            </div>
          )}
          {transcribeProgress !== null && (
            <div className="w-full mt-3">
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-green-500 h-2 rounded-full"
                  style={{ width: `${transcribeProgress}%` }}
                />
              </div>
              <div className="text-xs text-[var(--muted)] mt-1">
                Transcribing: {transcribeProgress}%
              </div>
            </div>
          )}
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
