import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { taskApi } from '../lib/api';
// 修复：区分 type 导入和 value 导入
import type { WorkflowStep, TaskProgress } from '../types';
import { TaskStatusEnum } from '../types';
import ResourceViewer from '../components/ResourceViewer';

const TaskWorkspace: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const [workflow, setWorkflow] = useState<WorkflowStep[]>([]);
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [viewingSegmentId, setViewingSegmentId] = useState<number | null>(null);
  const [resources, setResources] = useState<string[]>([]);
  const [resourceLoading, setResourceLoading] = useState(false);
  
  const timerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    taskApi.getWorkflow().then(res => {
      setWorkflow(res.data);
      if (res.data.length > 0) setViewingSegmentId(res.data[0].id);
    });
  }, []);

  const fetchProgress = useCallback(async () => {
    if (!taskId) return;
    try {
      const { data } = await taskApi.getProgress(taskId);
      setProgress(data);

      if (data.status.status === TaskStatusEnum.RUNNING) {
        timerRef.current = window.setTimeout(fetchProgress, 2000);
      }
      
      // 修复：删除了未使用的 currentSegId 变量
    } catch (e) {
      console.error("Fetch progress failed", e);
    }
  }, [taskId]);

  useEffect(() => {
    fetchProgress();
    return () => clearTimeout(timerRef.current);
  }, [fetchProgress]);

  useEffect(() => {
    if (!taskId || !viewingSegmentId) return;
    
    const currentSegId = progress ? parseInt(progress.current_segment) : 0;
    const isCompletedStep = viewingSegmentId < currentSegId || progress?.status.status === TaskStatusEnum.COMPLETED;
    
    if (isCompletedStep) {
      setResourceLoading(true);
      taskApi.getResource(taskId, viewingSegmentId)
        .then(res => setResources(res.data.urls))
        .catch(() => setResources([]))
        .finally(() => setResourceLoading(false));
    } else {
      setResources([]);
    }
  }, [taskId, viewingSegmentId, progress]);

  const handleExecute = async (redo: boolean = false) => {
    if (!taskId || !viewingSegmentId) return;
    try {
      await taskApi.execute(taskId, viewingSegmentId, redo);
      fetchProgress();
    } catch (e) {
      alert("执行请求失败");
    }
  };

  if (!taskId) return <div>Invalid Task ID</div>;

  const currentSegId = progress ? parseInt(progress.current_segment) : 0;
  const taskStatus = progress?.status.status;

  return (
    <div className="flex h-screen bg-gray-100 overflow-hidden">
      <div className="w-64 bg-white shadow-md flex flex-col">
        <div className="p-4 border-b">
          <Link to="/" className="text-gray-500 hover:text-gray-800 text-sm">&larr; 返回列表</Link>
          <h2 className="font-bold text-lg mt-2">Task: {taskId.substring(0, 6)}...</h2>
          <div className={`mt-2 inline-block px-2 py-1 text-xs rounded ${
            taskStatus === 'running' ? 'bg-blue-100 text-blue-800' : 
            taskStatus === 'completed' ? 'bg-green-100 text-green-800' : 
            taskStatus === 'failed' ? 'bg-red-100 text-red-800' : 'bg-gray-100'
          }`}>
            状态: {taskStatus}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {workflow.map(step => {
            const isActive = viewingSegmentId === step.id;
            const isPast = step.id < currentSegId;
            const isCurrent = step.id === currentSegId;
            
            return (
              <button
                key={step.id}
                onClick={() => setViewingSegmentId(step.id)}
                className={`w-full text-left px-4 py-3 rounded-md transition flex justify-between items-center ${
                  isActive ? 'bg-blue-50 border-blue-200 border text-blue-700' : 'hover:bg-gray-50 text-gray-600'
                }`}
              >
                <span>{step.id}. {step.name}</span>
                {isPast && <span className="text-green-500 text-xs">✓</span>}
                {isCurrent && taskStatus === 'running' && <span className="animate-spin text-blue-500 text-xs">⟳</span>}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white border-b p-4 flex justify-between items-center h-16">
          <h3 className="font-semibold text-gray-700">
            当前查看: {workflow.find(w => w.id === viewingSegmentId)?.name}
          </h3>
          
          <div className="space-x-3">
            {viewingSegmentId === currentSegId && taskStatus === 'pending' && (
              <button 
                onClick={() => handleExecute(false)}
                className="bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-700"
              >
                开始执行此步骤
              </button>
            )}
            
            {viewingSegmentId === currentSegId && taskStatus === 'running' && (
              <button disabled className="bg-gray-300 text-white px-4 py-2 rounded cursor-not-allowed">
                生成中...
              </button>
            )}

            {(viewingSegmentId && viewingSegmentId < currentSegId) || taskStatus === 'completed' ? (
              <button 
                onClick={() => handleExecute(true)}
                className="bg-orange-100 text-orange-700 border border-orange-200 px-4 py-2 rounded hover:bg-orange-200"
              >
                重做此步骤
              </button>
            ) : null}
          </div>
        </header>

        <main className="flex-1 overflow-auto p-6">
          {resourceLoading ? (
            <div className="flex justify-center items-center h-full text-gray-400">资源加载中...</div>
          ) : (
            viewingSegmentId && <ResourceViewer segmentId={viewingSegmentId} urls={resources} />
          )}
        </main>
      </div>
    </div>
  );
};

export default TaskWorkspace;