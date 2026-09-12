function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export type PresignedInfo = {
  url: string;
  object?: string;
  expires_at?: string;
  expires?: number;
};

export function asMinutesResult(result: unknown): Record<string, unknown> {
  if (!isRecord(result)) return {};
  const nested = result.result;
  return isRecord(nested) ? { ...result, ...nested } : result;
}

export function stringField(data: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === 'string' && value) return value;
  }
  return '';
}

export function asPresignedInfo(value: unknown): PresignedInfo | null {
  if (!isRecord(value) || typeof value.url !== 'string' || !value.url) return null;
  return {
    url: value.url,
    object: typeof value.object === 'string' ? value.object : undefined,
    expires_at: typeof value.expires_at === 'string' ? value.expires_at : undefined,
    expires: typeof value.expires === 'number' ? value.expires : undefined,
  };
}

export function formatActionItems(data: Record<string, unknown>): string {
  const items = data.action_items;
  if (Array.isArray(items)) {
    return items
      .map((item) => {
        if (typeof item === 'string') return item;
        if (isRecord(item) && typeof item.text === 'string') return item.text;
        return String(item);
      })
      .join('\n');
  }
  if (typeof items === 'string') return items;
  return stringField(data, 'todo');
}
