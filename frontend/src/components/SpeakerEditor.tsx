import { useEffect, useMemo, useState } from 'react';

import { updateTaskSpeakers } from '../api/client';
import {
  assignSpeaker,
  formatClock,
  knownSpeakers,
  speakerUpdates,
  transcriptSegments,
  type TranscriptSegment,
} from '../lib/speakers';

type SpeakerEditorProps = {
  taskId: string;
  segments: unknown;
  onSaved: (transcript: string, segments: TranscriptSegment[]) => void;
  onError: (message: string) => void;
};

export default function SpeakerEditor({ taskId, segments, onSaved, onError }: SpeakerEditorProps) {
  const initial = useMemo(() => transcriptSegments(segments), [segments]);
  const [rows, setRows] = useState<TranscriptSegment[]>(initial);
  const [selected, setSelected] = useState<number[]>([]);
  const [speakerName, setSpeakerName] = useState('');
  const [saving, setSaving] = useState(false);
  const names = knownSpeakers(rows);

  useEffect(() => {
    setRows(initial);
    setSelected([]);
  }, [initial]);

  if (!initial.length) return null;

  const toggle = (index: number) => {
    setSelected((current) =>
      current.includes(index) ? current.filter((item) => item !== index) : [...current, index]
    );
  };

  const applyName = () => {
    if (!selected.length || !speakerName.trim()) return;
    setRows((current) => assignSpeaker(current, selected, speakerName));
  };

  const save = async () => {
    const updates = speakerUpdates(initial, rows);
    if (!updates.length) return;
    setSaving(true);
    try {
      const saved = await updateTaskSpeakers(taskId, updates);
      onSaved(saved.transcript, transcriptSegments(saved.segments));
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Failed to save speaker names');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mb-4 rounded border border-slate-200 p-3">
      <div className="mb-2 text-sm font-medium">Speakers</div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          aria-label="Speaker name"
          list="known-speakers"
          value={speakerName}
          onChange={(event) => setSpeakerName(event.target.value)}
          placeholder="Speaker name"
          className="min-w-40 rounded border px-2 py-1 text-sm"
        />
        <datalist id="known-speakers">
          {names.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <button type="button" onClick={applyName} className="rounded border px-2 py-1 text-sm">
          Apply to selection
        </button>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="rounded bg-[var(--accent)] px-2 py-1 text-sm text-white disabled:opacity-60"
        >
          Save
        </button>
      </div>
      <ul className="space-y-2">
        {rows.map((segment, index) => (
          <li key={`${segment.start ?? 'start'}-${index}`} className="flex gap-2 text-sm">
            <input
              aria-label={`Select segment ${index + 1}`}
              type="checkbox"
              checked={selected.includes(index)}
              onChange={() => toggle(index)}
            />
            <div className="min-w-0 flex-1">
              <div className="text-xs text-[var(--muted)]">
                {formatClock(segment.start)}
                {segment.end != null ? `–${formatClock(segment.end)}` : ''}
                {segment.speaker ? ` ${segment.speaker}` : ' No speaker'}
              </div>
              <div className="whitespace-pre-wrap">{segment.text}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
