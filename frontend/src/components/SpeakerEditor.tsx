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
      onError(error instanceof Error ? error.message : '話者名の保存に失敗しました');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mb-4 rounded border border-slate-200 p-3">
      <div className="mb-2 text-sm font-medium">話者</div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          aria-label="話者名"
          list="known-speakers"
          value={speakerName}
          onChange={(event) => setSpeakerName(event.target.value)}
          placeholder="話者名"
          className="min-w-40 rounded border px-2 py-1 text-sm"
        />
        <datalist id="known-speakers">
          {names.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <button type="button" onClick={applyName} className="rounded border px-2 py-1 text-sm">
          選択範囲に適用
        </button>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="rounded bg-[var(--accent)] px-2 py-1 text-sm text-white disabled:opacity-60"
        >
          保存
        </button>
      </div>
      <ul className="space-y-2">
        {rows.map((segment, index) => (
          <li key={`${segment.start ?? 'start'}-${index}`} className="flex gap-2 text-sm">
            <input
              aria-label={`区間 ${index + 1} を選択`}
              type="checkbox"
              checked={selected.includes(index)}
              onChange={() => toggle(index)}
            />
            <div className="min-w-0 flex-1">
              <div className="text-xs text-[var(--muted)]">
                {formatClock(segment.start)}
                {segment.end != null ? `–${formatClock(segment.end)}` : ''}
                {segment.speaker ? ` ${segment.speaker}` : ' 話者なし'}
              </div>
              <div className="whitespace-pre-wrap">{segment.text}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
