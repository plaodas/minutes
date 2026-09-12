import type { components } from './generated';

export type ApiSchemas = components['schemas'];
export type TaskStage = ApiSchemas['TaskStage'];
export type TaskEventType = ApiSchemas['TaskEventType'];
export type TaskEventPayload = ApiSchemas['TaskEventPayload'];
export type StatusResponse = ApiSchemas['StatusResponse'];
export type ResultSuccess = ApiSchemas['ResultSuccess'];
export type CreateTaskResponse = ApiSchemas['CreateTaskResponse'];
export type AuthFeaturesResponse = ApiSchemas['AuthFeaturesResponse'];
export type AuthLoginResponse = ApiSchemas['AuthLoginResponse'];
export type TaskListItemResponse = ApiSchemas['TaskListItemResponse'];
export type TaskHistoryRecord = ApiSchemas['TaskHistoryRecord'];
export type TaskDeletedResponse = ApiSchemas['TaskDeletedResponse'];
export type TaskUndeletedResponse = ApiSchemas['TaskUndeletedResponse'];
export type ErrorResponse = ApiSchemas['ErrorResponse'];
