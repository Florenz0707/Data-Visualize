export interface User {
  id: string;
  username: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface Task {
  task_id: string;
}

export interface WorkflowStep {
  id: number;
  name: string;
}

export const TaskStatusEnum = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  DELETED: 'deleted'
} as const;

export type TaskStatusEnum = typeof TaskStatusEnum[keyof typeof TaskStatusEnum];

export interface TaskProgress {
  current_segment: number;
  status: TaskStatusEnum;
  workflow_version: 'default' | 'videogen';
  total_segments: number;
  segment_names: string[];
}

export interface TaskInfo {
  id: string | number;
  workflow_version: 'default' | 'videogen';
  status: TaskStatusEnum;
  current_segment: number;
  total_segments: number;
  segment_names: string[];
}

export interface ResourceResponse {
  segmentId: number;
  urls: string[];
}

export interface WSMessage {
  type: 'segment_finished' | 'segment_failed';
  task_id: string;
  segment_id: number;
  status: TaskStatusEnum;
  resources?: string[];
  error?: string;
}

export const SEGMENT_TYPE_MAP: Record<number, 'story_json' | 'image' | 'split_json' | 'audio' | 'video'> = {
  1: 'story_json',
  2: 'image',
  3: 'split_json',
  4: 'audio',
  5: 'video',
};

export const VIDEOGEN_SEGMENT_TYPE_MAP: Record<number, 'video'> = {
  1: 'video'
};
