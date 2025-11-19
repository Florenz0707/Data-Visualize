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

// 修复：将 enum 改为 const object + type
export const TaskStatusEnum = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed'
} as const;

export type TaskStatusEnum = typeof TaskStatusEnum[keyof typeof TaskStatusEnum];

export interface TaskProgress {
  current_segment: string; 
  status: {
    status: TaskStatusEnum;
  };
}

export interface ResourceResponse {
  segmentId: number;
  urls: string[];
}

export const SEGMENT_TYPE_MAP: Record<number, 'text' | 'image' | 'audio' | 'video'> = {
  1: 'text',
  2: 'image',
  3: 'text',
  4: 'audio',
  5: 'video',
};