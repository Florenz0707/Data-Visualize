import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, Link, useLocation } from 'react-router-dom';
import { taskApi, api } from '../lib/api';
import type { WorkflowStep, TaskProgress } from '../types';
import { TaskStatusEnum } from '../types';
import ResourceViewer, { type FetchFileFn } from '../components/ResourceViewer';
import { useWebSocket } from '../context/WebSocketContext';

const Spinner = () => (
  <svg className="animate-spin h-4 w-4 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
  </svg>
);

const TaskWorkspace: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const { lastMessage, isConnected } = useWebSocket();
  const location = useLocation();

  const [taskMode, setTaskMode] = useState<'story' | 'videogen'>('story');

  const [workflow, setWorkflow] = useState<WorkflowStep[]>([]);
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [viewingSegmentId, setViewingSegmentId] = useState<number | null>(null);
  const [resources, setResources] = useState<string[]>([]);
  const [resourceLoading, setResourceLoading] = useState(false);
  const [isLoadingProgress, setIsLoadingProgress] = useState(true);
  const [isInitialized, setIsInitialized] = useState(false);

  const [isAutoRun, setIsAutoRun] = useState(false);

  const [processingStepId, setProcessingStepId] = useState<number | null>(() => {
    if (!taskId) return null;
    const saved = localStorage.getItem(`processing_${taskId}`);
    return saved ? parseInt(saved) : null;
  });

  useEffect(() => {
    if (taskId) {
      if (processingStepId !== null) {
        localStorage.setItem(`processing_${taskId}`, processingStepId.toString());
      } else {
        localStorage.removeItem(`processing_${taskId}`);
      }
    }
  }, [processingStepId, taskId]);

  const timerRef = useRef<number | undefined>(undefined);
  const autoStartTriggeredRef = useRef(false);
  const lastProcessedMessageRef = useRef<any>(null);

  const resourcesCache = useRef<Map<number, string[]>>(new Map());
  const fileCache = useRef<Map<string, { data: any, type: 'blob' | 'json' }>>(new Map());

  const viewingSegmentIdRef = useRef<number | null>(null);
  useEffect(() => { viewingSegmentIdRef.current = viewingSegmentId; }, [viewingSegmentId]);

  const clearCaches = useCallback(() => {
    resourcesCache.current.clear();
    fileCache.current.clear();
  }, []);

  const fetchFile: FetchFileFn = useCallback(async (url, type, onProgress) => {
    if (fileCache.current.has(url)) {
      const cached = fileCache.current.get(url);
      if (cached?.type === type) {
        if (onProgress) onProgress(100);
        return Promise.resolve(cached.data);
      }
    }

    const res = await api.get('/resource', {
      params: { url },
      responseType: type === 'json' ? 'json' : 'blob',
      onDownloadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded * 100) / event.total));
        }
      }
    });

    fileCache.current.set(url, { data: res.data, type });
    return res.data;
  }, []);

  const fetchSegmentResources = useCallback(async (segId: number): Promise<string[]> => {
    if (!taskId) return [];
    if (resourcesCache.current.has(segId)) {
      return resourcesCache.current.get(segId) || [];
    }
    try {
      const res = await taskApi.getResource(taskId, segId);
      const urls = res.data.urls || [];
      resourcesCache.current.set(segId, urls);
      return urls;
    } catch (e) {
      console.error(`Failed to fetch resources for segment ${segId}`);
      return [];
    }
  }, [taskId]);

  const getCompletedSegId = useCallback((p: TaskProgress | null) => {
    if (!p) return 0;
    if (p.status === TaskStatusEnum.COMPLETED) {
      return p.total_segments || (workflow.length > 0 ? workflow.length : p.current_segment);
    }
    return p.current_segment;
  }, [workflow.length]);

  const fetchProgress = useCallback(async () => {
    if (!taskId) return;
    try {
      const { data } = await taskApi.getProgress(taskId);
      setProgress(data);

      setProcessingStepId(prev => {
        if (prev !== null) {
          if (data.status === TaskStatusEnum.COMPLETED || data.status === TaskStatusEnum.FAILED) {
            return null;
          }
        }
        return prev;
      });

      if (data.segment_names && (workflow.length === 0 || data.workflow_version !== (taskMode === 'story' ? 'default' : 'videogen'))) {
        const steps = data.segment_names.map((name, index) => ({
          id: index + 1,
          name: name
        }));
        setWorkflow(steps);
        const mode = data.workflow_version === 'videogen' ? 'videogen' : 'story';
        setTaskMode(mode);

        setViewingSegmentId(prev => {
            if (prev) return prev;
            const current = data.current_segment;
            const status = data.status;
            if (status === TaskStatusEnum.RUNNING) return current + 1;
            return Math.min(current + 1, steps.length);
        });
        setIsInitialized(true);
      }
    } catch (e) {
      console.error("Fetch progress failed", e);
    } finally {
      setIsLoadingProgress(false);
    }
  }, [taskId, workflow.length, taskMode]);

  useEffect(() => {
    fetchProgress();
    return () => clearTimeout(timerRef.current);
  }, [fetchProgress]);

  useEffect(() => {
    if (isConnected) {
      fetchProgress();
    }
  }, [isConnected, fetchProgress]);

  const loadResources = useCallback(async (segId: number, force: boolean = false) => {
    if (!taskId) return;

    if (force) {
      resourcesCache.current.delete(segId);
    }

    if (resourcesCache.current.has(segId)) {
      if (viewingSegmentIdRef.current === segId) {
        setResources(resourcesCache.current.get(segId) || []);
        setResourceLoading(false);
      }
      return;
    }

    if (viewingSegmentIdRef.current === segId) {
      setResourceLoading(true);
    }

    const urls = await fetchSegmentResources(segId);

    if (viewingSegmentIdRef.current === segId) {
      setResources(urls);
      setResourceLoading(false);
    }
  }, [taskId, fetchSegmentResources]);

  const executeStep = async (segId: number, redo: boolean = false) => {
    if (!taskId) return;
    try {
      setProcessingStepId(segId);

      if (redo) {
        resourcesCache.current.delete(segId);
        fileCache.current.clear();
      }

      setProgress(prev => prev ? ({ ...prev, status: TaskStatusEnum.RUNNING }) : null);
      await taskApi.execute(taskId, segId, redo);

      setTimeout(fetchProgress, 1000);

    } catch (e) {
      console.error("Execute failed", e);
      alert("Request failed");
      setProcessingStepId(null);
      fetchProgress();
    }
  };

  useEffect(() => {
    if (!lastMessage || !taskId) return;

    if (lastMessage === lastProcessedMessageRef.current) return;
    lastProcessedMessageRef.current = lastMessage;

    if (lastMessage.task_id == taskId) {
      if (lastMessage.type === 'segment_finished' || lastMessage.type === 'segment_failed') {
        setProcessingStepId(null);
      }

      if (lastMessage.type === 'segment_finished') {
        resourcesCache.current.delete(lastMessage.segment_id);
        fileCache.current.clear();

        setProgress(prev => {
            if (!prev) return null;
            const isLastStep = lastMessage.segment_id >= workflow.length;
            return {
                ...prev,
                current_segment: lastMessage.segment_id,
                status: isLastStep ? TaskStatusEnum.COMPLETED : TaskStatusEnum.PENDING
            };
        });

        setTimeout(() => fetchProgress(), 500);

        if (lastMessage.segment_id === viewingSegmentId) {
          loadResources(viewingSegmentId, true);
        }

        if (isAutoRun) {
            const nextStepId = lastMessage.segment_id + 1;
            if (workflow.find(w => w.id === nextStepId)) {
                setTimeout(() => {
                    executeStep(nextStepId, false);
                }, 1000);
            } else {
                setIsAutoRun(false);
            }
        }
      } else {
        fetchProgress();
      }
    }
  }, [lastMessage, taskId, viewingSegmentId, fetchProgress, loadResources, isAutoRun, workflow]);

  useEffect(() => {
    if (!taskId || !viewingSegmentId) return;
    const completedSegId = getCompletedSegId(progress);

    if (viewingSegmentId <= completedSegId) {
       if (!resourcesCache.current.has(viewingSegmentId)) {
         setResources([]);
       }
       loadResources(viewingSegmentId);
    } else {
      setResources([]);
    }
  }, [taskId, viewingSegmentId, progress, loadResources, getCompletedSegId]);

  const handleExecuteClick = (redo: boolean = false) => {
    if (viewingSegmentId) executeStep(viewingSegmentId, redo);
  };

  const handleResourceUpdate = () => {
    clearCaches();
    fetchProgress();
    if (viewingSegmentId) loadResources(viewingSegmentId, true);
  };

  useEffect(() => {
    const shouldAutoStart = location.state?.autoStart;

    if (shouldAutoStart && !autoStartTriggeredRef.current && isInitialized && progress && workflow.length > 0) {
        const completedSegId = getCompletedSegId(progress);
        const isPending = progress.status === TaskStatusEnum.PENDING;

        if (completedSegId === 0 && isPending) {
            autoStartTriggeredRef.current = true;
            setIsAutoRun(true);

            const firstStepId = workflow[0].id;
            setViewingSegmentId(firstStepId);
            executeStep(firstStepId, false);
        }
    } else if (shouldAutoStart && !autoStartTriggeredRef.current && isInitialized && progress) {
        if (progress.status === TaskStatusEnum.RUNNING || progress.current_segment < workflow.length) {
             setIsAutoRun(true);
             autoStartTriggeredRef.current = true;
        }
    }
  }, [location.state, isInitialized, progress, workflow, getCompletedSegId]);

  if (!taskId) return <div>Invalid Task ID</div>;

  const completedSegId = getCompletedSegId(progress);
  const taskStatus = progress?.status;

  const nextStepId = completedSegId + 1;

  const isStepProcessing = (stepId: number) => stepId === processingStepId;

  let displayStatus = 'UNKNOWN';
  if (isLoadingProgress) {
    displayStatus = 'LOADING...';
  } else if (processingStepId !== null) {
    displayStatus = 'RUNNING';
  } else if (taskStatus === TaskStatusEnum.RUNNING) {
    displayStatus = 'PENDING';
  } else {
    displayStatus = taskStatus?.toUpperCase() || 'UNKNOWN';
  }

  return (
    <div className="flex h-screen bg-gray-100 overflow-hidden">
      <div className="w-64 bg-white shadow-md flex flex-col z-10">
        <div className="p-4 border-b bg-gray-50">
          <Link to="/" className="text-gray-500 hover:text-gray-800 text-sm flex items-center gap-1">
            &larr; 返回列表
          </Link>
          <div className="flex items-center gap-2 mt-3">
            <h2 className="font-bold text-lg text-gray-800">
               {taskMode === 'videogen' ? '视频生成任务' : '故事生成任务'}
            </h2>
          </div>
          <div className="text-xs text-gray-400 font-mono mb-2">{taskId}</div>

          <div className="flex flex-col gap-2 mt-2">
             <div className={`px-2 py-0.5 text-xs rounded-full border text-center ${
              displayStatus === 'RUNNING' ? 'bg-blue-50 border-blue-200 text-blue-700' :
              displayStatus === 'COMPLETED' ? 'bg-green-50 border-green-200 text-green-700' :
              displayStatus === 'FAILED' ? 'bg-red-50 border-red-200 text-red-700' :
              displayStatus === 'DELETED' ? 'bg-gray-200 border-gray-300 text-gray-600' :
              'bg-gray-100 border-gray-200'
            }`}>
              {displayStatus}
            </div>

            <div className="flex justify-between items-center px-1">
                <div className="flex items-center gap-1 text-xs text-gray-500">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-400'}`}></div>
                    <span>{isConnected ? 'WS Connected' : 'WS Disconnected'}</span>
                </div>

                <label className="flex items-center gap-1 cursor-pointer" title="当前步骤完成后自动执行下一步">
                    <input
                        type="checkbox"
                        className="w-3 h-3"
                        checked={isAutoRun}
                        onChange={(e) => setIsAutoRun(e.target.checked)}
                    />
                    <span className="text-xs font-medium text-gray-600">自动执行</span>
                </label>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {workflow.length === 0 && !isLoadingProgress && <div className="p-4 text-gray-400 text-sm">加载工作流...</div>}
          {workflow.map(step => {
            const isActive = viewingSegmentId === step.id;
            const isCompleted = step.id <= completedSegId;
            const isRunning = isStepProcessing(step.id);

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
                {isRunning && (
                  <div className="flex items-center justify-center w-5 h-5">
                    <Spinner />
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
        <header className="bg-white border-b px-6 py-3 flex justify-between items-center h-16 shadow-sm z-20 relative">
          <h3 className="font-bold text-xl text-gray-800">
            {workflow.find(w => w.id === viewingSegmentId)?.name || '...'}
          </h3>

          <div className="space-x-3">
            {viewingSegmentId === nextStepId && processingStepId === null && (
              <button
                onClick={() => handleExecuteClick(false)}
                className="bg-blue-600 text-white px-6 py-2 rounded-full shadow hover:bg-blue-700 active:scale-95 transition font-medium"
              >
                开始生成
              </button>
            )}

            {viewingSegmentId === nextStepId && processingStepId === nextStepId && (
              <button disabled className="bg-gray-100 text-gray-400 border border-gray-200 px-6 py-2 rounded-full cursor-not-allowed flex items-center gap-2">
                <Spinner />
                生成中...
              </button>
            )}

            {viewingSegmentId !== null && viewingSegmentId <= completedSegId && processingStepId === null && (
              <button
                onClick={() => handleExecuteClick(true)}
                className="text-orange-600 border border-orange-200 bg-orange-50 px-4 py-2 rounded-full hover:bg-orange-100 transition text-sm font-medium"
              >
                重新生成此步骤
              </button>
            )}

            {viewingSegmentId !== null && viewingSegmentId <= completedSegId && processingStepId === viewingSegmentId && (
               <button disabled className="bg-gray-100 text-gray-400 border border-gray-200 px-6 py-2 rounded-full cursor-not-allowed flex items-center gap-2">
                <Spinner />
                重做中...
              </button>
            )}
          </div>
        </header>

        <main className="flex-1 overflow-auto">
          {resourceLoading ? (
            <div className="flex flex-col justify-center items-center h-64 text-gray-400 space-y-3">
              <div className="w-8 h-8 border-4 border-gray-200 border-t-blue-500 rounded-full animate-spin"></div>
              <p>获取资源中...</p>
            </div>
          ) : (
            viewingSegmentId && (
              <ResourceViewer
                key={viewingSegmentId}
                taskId={taskId}
                segmentId={viewingSegmentId}
                urls={resources}
                taskMode={taskMode}
                completedSegId={completedSegId}
                onResourceUpdate={handleResourceUpdate}
                fetchFile={fetchFile}
                fetchSegmentResources={fetchSegmentResources}
              />
            )
          )}
        </main>
      </div>
    </div>
  );
};

export default TaskWorkspace;
