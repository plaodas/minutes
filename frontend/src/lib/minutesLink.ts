const MINUTES_HASH = /^#minutes=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;

export function minutesTaskIdFromHash(hash: string): string | null {
  const match = MINUTES_HASH.exec(hash);
  return match ? match[1] : null;
}

export function minutesHash(taskId: string): string {
  return `#minutes=${taskId}`;
}
