export type AppToastDetail = {
  type: 'info' | 'success' | 'error';
  message: string;
};

export type ConfirmDeleteDetail = {
  taskId?: string;
};

export function dispatchAppToast(detail: AppToastDetail): void {
  window.dispatchEvent(new CustomEvent<AppToastDetail>('appToast', { detail }));
}

export function dispatchTaskChanged(taskId: string, action: string): void {
  window.dispatchEvent(new CustomEvent('app:task-changed', { detail: { taskId, action } }));
}
