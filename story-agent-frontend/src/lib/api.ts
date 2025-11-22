import axios from 'axios';
import type { WorkflowStep, TaskProgress, ResourceResponse } from '../types';

const API_BASE_URL = '/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    const isLoginRequest = originalRequest.url?.includes('/login');

    if (error.response?.status === 401 && !originalRequest._retry && !isLoginRequest) {
      originalRequest._retry = true;
      try {
        const { data } = await axios.post(`${API_BASE_URL}/refresh`);
        localStorage.setItem('access_token', data.access_token);
        api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        localStorage.removeItem('access_token');
        if (!window.location.pathname.includes('/login')) {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: (data: any) => api.post('/login', data),
  register: (data: any) => api.post('/register', data),
};

export const taskApi = {
  getWorkflow: () => api.get<WorkflowStep[]>('/task/workflow'),
  create: (data: { topic: string; main_role?: string; scene?: string; workflow_version?: string }) => api.post('/task/new', data),
  getMyTasks: () => api.get<{ task_ids: string[] }>('/task/mytasks'),
  getProgress: (taskId: string) => api.get<TaskProgress>(`/task/${taskId}/progress`),
  getResource: (taskId: string, segmentId: number) => api.get<ResourceResponse>(`/task/${taskId}/resource`, { params: { segmentId } }),
  execute: (taskId: string, segmentId: number, redo = false) => api.post(`/task/${taskId}/execute/${segmentId}`, null, { params: { redo } }),
  delete: (taskId: string) => api.delete(`/task/${taskId}`),
  updateResource: (taskId: string, segmentId: number, data: any) => api.put(`/task/${taskId}/myresource/${segmentId}`, data),
};