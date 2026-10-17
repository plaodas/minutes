export type AddToast = (
  msg: string,
  opts?: {
    level?: 'info' | 'success' | 'error';
    duration?: number;
    actionLabel?: string;
    action?: () => void;
  }
) => string;

export type Runner = () => Promise<{ blob: Blob; headers?: Headers }>;

export async function startDownload(
  runner: Runner,
  filename: string,
  addToast: AddToast,
  successMsg = 'ダウンロードを開始しました'
) {
  try {
    const { blob } = await runner();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    addToast(successMsg, { level: 'info', duration: 3000 });
  } catch (e: unknown) {
    const message = e instanceof Error && e.message ? e.message : String(e);
    addToast('ダウンロードに失敗しました: ' + message, {
      level: 'error',
      actionLabel: '再試行',
      action: () => startDownload(runner, filename, addToast, successMsg),
    });
  }
}

export default startDownload;
