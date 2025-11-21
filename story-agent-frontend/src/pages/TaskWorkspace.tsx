import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, Link, useLocation } from 'react-router-dom';
import { taskApi } from '../lib/api';
import type { WorkflowStep, TaskProgress } from '../types';
import { TaskStatusEnum } from '../types';
import ResourceViewer from '../components/ResourceViewer';
import { useWebSocket } from '../context/WebSocketContext';

const TaskWorkspace: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const { lastMessage, isConnected } = useWebSocket();
  const location = useLocation();
  
  const [workflow, setWorkflow] = useState<WorkflowStep[]>([]);
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [viewingSegmentId, setViewingSegmentId] = useState<number | null>(null);
  const [resources, setResources] = useState<string[]>([]);
  const [resourceLoading, setResourceLoading] = useState(false);
  
  const timerRef = useRef<number | undefined>(undefined);
  const autoStartRef = useRef(false);

  // 1. 初始化：加载工作流定义
  useEffect(() => {
    taskApi.getWorkflow().then(res => {
      setWorkflow(res.data);
      if (res.data.length > 0) setViewingSegmentId(res.data[0].id);
    });
  }, []);

  // 2. 获取任务进度的核心函数
  const fetchProgress = useCallback(async () => {
    if (!taskId) return;
    try {
      const { data } = await taskApi.getProgress(taskId);
      setProgress(data);

      if (data.status.status === TaskStatusEnum.RUNNING) {
        clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(fetchProgress, 3000);
      }
    } catch (e) {
      console.error("Fetch progress failed", e);
    }
  }, [taskId]);

  // 3. 监听 WebSocket 消息
  useEffect(() => {
    if (!lastMessage || !taskId) return;

    if (lastMessage.task_id == taskId) {
      console.log("收到当前任务更新:", lastMessage);
      fetchProgress();
      
      if (lastMessage.type === 'segment_finished' && lastMessage.segment_id === viewingSegmentId) {
        loadResources(viewingSegmentId);
      }
    }
  }, [lastMessage, taskId]);

  // 4. 初始加载进度
  useEffect(() => {
    fetchProgress();
    return () => clearTimeout(timerRef.current);
  }, [fetchProgress]);

  // 5. 加载资源逻辑
  const loadResources = useCallback((segId: number) => {
    if (!taskId) return;
    setResourceLoading(true);
    taskApi.getResource(taskId, segId)
      .then(res => setResources(res.data.urls))
      .catch(() => setResources([]))
      .finally(() => setResourceLoading(false));
  }, [taskId]);

  // 6. 自动切换资源逻辑
  useEffect(() => {
    if (!taskId || !viewingSegmentId) return;
    
    const completedSegId = progress ? parseInt(progress.current_segment || '0') : 0;
    if (viewingSegmentId <= completedSegId) {
       loadResources(viewingSegmentId);
    } else {
      setResources([]);
    }
  }, [taskId, viewingSegmentId, progress, loadResources]);

  // 抽象出执行函数
  const executeStep = async (segId: number, redo: boolean = false) => {
    if (!taskId) return;
    try {
      await taskApi.execute(taskId, segId, redo);
      setProgress(prev => prev ? ({ ...prev, status: { status: TaskStatusEnum.RUNNING } }) : null);
    } catch (e) {
      console.error("执行失败", e);
      alert("任务启动失败，请手动重试");
    }
  };

  const handleExecuteClick = (redo: boolean = false) => {
    if (viewingSegmentId) executeStep(viewingSegmentId, redo);
  };

  useEffect(() => {
    const autoStart = location.state?.autoStart;
    // 条件：需要自动执行 + 还没执行过 + 工作流已加载 + 进度已加载
    if (autoStart && !autoStartRef.current && workflow.length > 0 && progress) {
        const completedSegId = parseInt(progress.current_segment || '0');
        // 只有当任务完全处于初始状态（完成阶段为0 且 状态为 PENDING）时才自动执行
        if (completedSegId === 0 && progress.status.status === TaskStatusEnum.PENDING) {
            console.log("Auto starting new task...");
            autoStartRef.current = true;
            const firstStepId = workflow[0].id;
            setViewingSegmentId(firstStepId);
            executeStep(firstStepId, false);
        }
    }
  }, [location.state, workflow, progress]);

  if (!taskId) return <div>Invalid Task ID</div>;

  // current_segment 代表“已完成”的最新阶段
  const completedSegId = progress ? parseInt(progress.current_segment || '0') : 0;
  const taskStatus = progress?.status.status;
  const nextStepId = completedSegId + 1;
  const runningStepId = taskStatus === TaskStatusEnum.RUNNING ? nextStepId : null;

  return (
    <div className="flex h-screen bg-gray-100 overflow-hidden">
      <div className="w-64 bg-white shadow-md flex flex-col z-10">
        <div className="p-4 border-b bg-gray-50">
          <Link to="/" className="text-gray-500 hover:text-gray-800 text-sm flex items-center gap-1">
            &larr; 返回列表
          </Link>
          <h2 className="font-bold text-lg mt-3 text-gray-800">Task Workspace</h2>
          <div className="text-xs text-gray-400 font-mono mb-2">{taskId}</div>
          
          <div className="flex justify-between items-center mt-2">
             <div className={`px-2 py-0.5 text-xs rounded-full border ${
              taskStatus === 'running' ? 'bg-blue-50 border-blue-200 text-blue-700' : 
              taskStatus === 'completed' ? 'bg-green-50 border-green-200 text-green-700' : 
              taskStatus === 'failed' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-gray-100 border-gray-200'
            }`}>
              {taskStatus?.toUpperCase() || 'UNKNOWN'}
            </div>
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-400'}`} title={isConnected ? "WebSocket Connected" : "Disconnected"}></div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {workflow.map(step => {
            const isActive = viewingSegmentId === step.id;
            const isCompleted = step.id <= completedSegId;
            const isRunning = step.id === runningStepId;
            
            return (
              <button
                key={step.id}
                onClick={() => setViewingSegmentId(step.id)}
                className={`w-full text-left px-4 py-3 rounded-lg transition-all duration-200 flex justify-between items-center group ${
                  isActive ? 'bg-blue-600 text-white shadow-md' : 'hover:bg-gray-100 text-gray-600'
                }`}
              >
                <span className="font-medium">{step.id}. {step.name}</span>
                {isCompleted && <span className={isActive ? 'text-blue-200' : 'text-green-500'}>✓</span>}
                {isRunning && <span className="animate-spin">⟳</span>}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
        <header className="bg-white border-b px-6 py-3 flex justify-between items-center h-16 shadow-sm">
          <h3 className="font-bold text-xl text-gray-800">
            {workflow.find(w => w.id === viewingSegmentId)?.name}
          </h3>
          
          <div className="space-x-3">
            {/* 场景1：显示“开始生成” */}
            {viewingSegmentId === nextStepId && taskStatus !== TaskStatusEnum.RUNNING && (
              <button 
                onClick={() => handleExecuteClick(false)}
                className="bg-blue-600 text-white px-6 py-2 rounded-full shadow hover:bg-blue-700 active:scale-95 transition font-medium"
              >
                开始生成
              </button>
            )}
            
            {/* 场景2：显示“生成中” */}
            {viewingSegmentId === runningStepId && (
              <button disabled className="bg-gray-100 text-gray-400 border border-gray-200 px-6 py-2 rounded-full cursor-not-allowed flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin"></span>
                生成中...
              </button>
            )}

            {/* 场景3：显示“重新生成” */}
            {viewingSegmentId !== null && viewingSegmentId <= completedSegId && taskStatus !== TaskStatusEnum.RUNNING && (
              <button 
                onClick={() => handleExecuteClick(true)}
                className="text-orange-600 border border-orange-200 bg-orange-50 px-4 py-2 rounded-full hover:bg-orange-100 transition text-sm font-medium"
              >
                重新生成此步骤
              </button>
            )}
          </div>
        </header>

        <main className="flex-1 overflow-auto p-8">
          {resourceLoading ? (
            <div className="flex flex-col justify-center items-center h-64 text-gray-400 space-y-3">
              <div className="w-8 h-8 border-4 border-gray-200 border-t-blue-500 rounded-full animate-spin"></div>
              <p>获取资源中...</p>
            </div>
          ) : (
            viewingSegmentId && <ResourceViewer segmentId={viewingSegmentId} urls={resources} />
          )}
        </main>
      </div>
    </div>
  );
};

export default TaskWorkspace;