export type TranscriptSegment = {
  start?: number;
  end?: number;
  text: string;
  speaker?: string;
};

export function transcriptSegments(value: unknown): TranscriptSegment[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== 'object' || item === null) return [];
    const record = item as Record<string, unknown>;
    const text = typeof record.text === 'string' ? record.text : '';
    const segment: TranscriptSegment = { text };
    if (typeof record.start === 'number') segment.start = record.start;
    if (typeof record.end === 'number') segment.end = record.end;
    if (typeof record.speaker === 'string' && record.speaker.trim()) {
      segment.speaker = record.speaker.trim();
    }
    return [segment];
  });
}

export function knownSpeakers(segments: TranscriptSegment[]): string[] {
  const names: string[] = [];
  for (const segment of segments) {
    const speaker = segment.speaker?.trim();
    if (speaker && !names.includes(speaker)) names.push(speaker);
  }
  return names;
}

export function assignSpeaker(
  segments: TranscriptSegment[],
  indexes: number[],
  speaker: string
): TranscriptSegment[] {
  const name = speaker.trim();
  const selected = new Set(indexes);
  return segments.map((segment, index) =>
    selected.has(index) ? { ...segment, speaker: name || undefined } : segment
  );
}

export function speakerUpdates(before: TranscriptSegment[], after: TranscriptSegment[]) {
  return after.flatMap((segment, index) => {
    const next = segment.speaker?.trim() || '';
    const previous = before[index]?.speaker?.trim() || '';
    if (!next || next === previous) return [];
    return [{ index, speaker: next }];
  });
}

export function formatClock(seconds: number | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '';
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}
