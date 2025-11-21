import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../lib/api';

const Login: React.FC = () => {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (isRegister) {
        await authApi.register({ username, password });
        await login({ username, password });
      } else {
        await login({ username, password });
      }
      navigate('/');
    } catch (err: any) {
      console.error(err);
      const msg = err.response?.data?.detail || err.message;
      setError(isRegister ? `注册失败: ${msg}` : '登录失败，请检查用户名密码');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="bg-white p-10 rounded-xl shadow-xl w-96 border border-gray-100">
        <h2 className="text-3xl font-extrabold mb-8 text-center text-gray-800">
          {isRegister ? '创建账号' : '欢迎回来'}
        </h2>
        {error && <div className="bg-red-50 text-red-600 p-3 mb-6 rounded-lg text-sm border border-red-100">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">用户名</label>
            <input
              type="text"
              className="w-full border border-gray-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">密码</label>
            <input
              type="password"
              className="w-full border border-gray-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition shadow-md">
            {isRegister ? '注册并自动登录' : '立即登录'}
          </button>
        </form>
        <div className="mt-6 text-center">
          <button 
            className="text-sm text-blue-600 hover:text-blue-800 font-medium hover:underline"
            onClick={() => {
              setIsRegister(!isRegister);
              setError('');
            }}
          >
            {isRegister ? '已有账号？去登录' : '没有账号？去注册'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Login;