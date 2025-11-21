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
      navigate(`/task/${data.task_id}`);
    } catch (error) {
      alert('创建失败');
    }
  };

  const handleDelete = async (e: React.MouseEvent, taskId: string) => {
    e.preventDefault();
    if (!window.confirm('确定要删除这个任务吗？此操作不可恢复。')) return;
    
    try {
      await taskApi.delete(taskId);
      setTasks(prev => prev.filter(id => id !== taskId));
    } catch (error) {
      alert('删除失败');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow p-4 flex justify-between items-center">
        <h1 className="text-xl font-bold text-gray-800">我的故事工作台</h1>
        <button onClick={logout} className="text-red-500 hover:text-red-700 text-sm font-medium transition">退出登录</button>
      </header>

      <main className="container mx-auto p-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-lg font-semibold text-gray-700">任务列表</h2>
          <button 
            onClick={() => setShowModal(true)}
            className="bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-700 transition flex items-center gap-2"
          >
            <span>+</span> 新建故事任务
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {tasks.map((taskId) => (
            <Link key={taskId} to={`/task/${taskId}`} className="block group relative">
              <div className="bg-white p-6 rounded-lg shadow-sm hover:shadow-md transition border border-gray-200 group-hover:border-blue-300">
                <div className="flex justify-between items-start mb-2">
                    <div className="font-mono text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">ID: {taskId}</div>
                    
                    {/* 删除按钮 */}
                    <button 
                        onClick={(e) => handleDelete(e, taskId)}
                        className="text-gray-300 hover:text-red-500 p-1 rounded-full hover:bg-red-50 transition z-10"
                        title="删除任务"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                        </svg>
                    </button>
                </div>
                <div className="text-gray-800 font-medium text-lg mb-4">故事生成任务</div>
                <div className="text-blue-600 group-hover:translate-x-1 transition-transform inline-block text-sm font-semibold">进入工作区 &rarr;</div>
              </div>
            </Link>
          ))}
          {tasks.length === 0 && (
            <div className="text-gray-400 col-span-full text-center py-16 bg-white rounded-lg border border-dashed border-gray-300">
                <p>暂无任务，点击右上角创建</p>
            </div>
          )}
        </div>
      </main>

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-lg w-96 shadow-xl transform transition-all">
            <h3 className="text-lg font-bold mb-4 text-gray-800">新建任务</h3>
            <div className="space-y-3">
              <input 
                className="w-full border border-gray-300 p-2 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none" 
                placeholder="主题 (必填)" 
                value={newTopic} 
                onChange={e => setNewTopic(e.target.value)} 
              />
              <input 
                className="w-full border border-gray-300 p-2 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none" 
                placeholder="主角 (选填)" 
                value={role} 
                onChange={e => setRole(e.target.value)} 
              />
              <input 
                className="w-full border border-gray-300 p-2 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none" 
                placeholder="场景 (选填)" 
                value={scene} 
                onChange={e => setScene(e.target.value)} 
              />
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowModal(false)} className="text-gray-500 px-4 py-2 hover:bg-gray-100 rounded transition">取消</button>
              <button onClick={handleCreate} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition shadow">创建</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;