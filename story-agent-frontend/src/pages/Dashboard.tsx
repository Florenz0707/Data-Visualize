import React, { useEffect, useState } from 'react';
import { taskApi } from '../lib/api';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const Dashboard: React.FC = () => {
  const [tasks, setTasks] = useState<string[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [newTopic, setNewTopic] = useState('');
  const [role, setRole] = useState('');
  const [scene, setScene] = useState('');
  const { logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    fetchTasks();
  }, []);

  const fetchTasks = async () => {
    try {
      const { data } = await taskApi.getMyTasks();
      setTasks(data.task_ids || []);
    } catch (error) {
      console.error(error);
    }
  };

  const handleCreate = async () => {
    if (!newTopic) return;
    try {
      const { data } = await taskApi.create({ topic: newTopic, main_role: role, scene });
      setShowModal(false);
      // 直接跳转到新任务
      navigate(`/task/${data.task_id}`);
    } catch (error) {
      alert('创建失败');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow p-4 flex justify-between items-center">
        <h1 className="text-xl font-bold">我的故事工作台</h1>
        <button onClick={logout} className="text-red-500 text-sm">退出登录</button>
      </header>

      <main className="container mx-auto p-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-lg font-semibold">任务列表</h2>
          <button 
            onClick={() => setShowModal(true)}
            className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
          >
            + 新建故事任务
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {tasks.map((taskId) => (
            <Link key={taskId} to={`/task/${taskId}`} className="block group">
              <div className="bg-white p-6 rounded-lg shadow-sm hover:shadow-md transition border border-gray-200">
                <div className="font-mono text-sm text-gray-500 mb-2">ID: {taskId}</div>
                <div className="text-blue-600 group-hover:underline font-medium">进入工作区 &rarr;</div>
              </div>
            </Link>
          ))}
          {tasks.length === 0 && <div className="text-gray-400 col-span-full text-center py-10">暂无任务，点击右上角创建</div>}
        </div>
      </main>

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-lg w-96">
            <h3 className="text-lg font-bold mb-4">新建任务</h3>
            <div className="space-y-3">
              <input 
                className="w-full border p-2 rounded" 
                placeholder="主题 (必填)" 
                value={newTopic} 
                onChange={e => setNewTopic(e.target.value)} 
              />
              <input 
                className="w-full border p-2 rounded" 
                placeholder="主角 (选填)" 
                value={role} 
                onChange={e => setRole(e.target.value)} 
              />
              <input 
                className="w-full border p-2 rounded" 
                placeholder="场景 (选填)" 
                value={scene} 
                onChange={e => setScene(e.target.value)} 
              />
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowModal(false)} className="text-gray-500 px-3 py-1">取消</button>
              <button onClick={handleCreate} className="bg-blue-600 text-white px-4 py-1 rounded">创建</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;