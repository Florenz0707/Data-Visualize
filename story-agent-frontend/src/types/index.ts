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

// WebSocket 消息类型定义
export interface WSMessage {
  type: 'segment_finished' | 'segment_failed';
  task_id: string;
  segment_id: number;
  status: TaskStatusEnum;
  resources?: string[];
  error?: string;
}

export const SEGMENT_TYPE_MAP: Record<number, 'story_json' | 'image' | 'split_json' | 'audio' | 'video'> = {
  1: 'story_json', // Story (JSON)
  2: 'image',      // Image
  3: 'split_json', // Split (JSON)
  4: 'audio',      // Speech
  5: 'video',      // Video
};

export const VIDEOGEN_SEGMENT_TYPE_MAP: Record<number, 'video'> = {
  1: 'video'
};