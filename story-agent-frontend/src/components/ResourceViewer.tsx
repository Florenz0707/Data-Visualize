import React, { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { SEGMENT_TYPE_MAP } from '../types';

interface Props {
  segmentId: number;
  urls: string[];
}

const useSecureResource = (url: string) => {
  const [objectUrl, setObjectUrl] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    let currentUrl = '';

    const fetchResource = async () => {
      try {
        setLoading(true);
        setError(false);
        const response = await api.get('/resource', { 
          params: { url },
          responseType: 'blob' 
        });
        
        if (active) {
          const blobUrl = URL.createObjectURL(response.data);
          currentUrl = blobUrl;
          setObjectUrl(blobUrl);
        }
      } catch (e) {
        console.error("Resource load failed", e);
        if (active) setError(true);
      } finally {
        if (active) setLoading(false);
      }
    };

    if (url) {
      fetchResource();
    }

    return () => {
      active = false;
      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
      }
    };
  }, [url]);

  return { objectUrl, loading, error };
};

// 1. 图片组件
const SecureImage: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);

  if (loading) return <div className="w-full h-48 bg-gray-100 animate-pulse rounded flex items-center justify-center text-gray-400">加载图片...</div>;
  if (!objectUrl) return <div className="w-full h-48 bg-gray-100 rounded flex items-center justify-center text-gray-400">图片加载失败</div>;
  
  return <img src={objectUrl} alt="Generated" className="w-full h-auto rounded shadow hover:shadow-lg transition" />;
};

// 2. 音频组件
const SecureAudio: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);

  if (loading) return <div className="p-4 bg-gray-50 rounded animate-pulse text-sm text-gray-500">加载音频中...</div>;
  
  return (
    <div className="bg-white p-3 rounded shadow flex items-center border border-gray-100">
      <audio controls className="w-full h-10" src={objectUrl}>
        您的浏览器不支持音频播放
      </audio>
    </div>
  );
};

// 3. 视频组件
const SecureVideo: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);

  if (loading) return <div className="w-full aspect-video bg-gray-800 rounded-lg animate-pulse flex items-center justify-center text-gray-400">加载视频中...</div>;

  return (
    <video controls className="w-full rounded-lg shadow-xl bg-black aspect-video" src={objectUrl}>
      您的浏览器不支持视频播放
    </video>
  );
};

// 4. JSON 内容查看器 (用于 Story 和 Split)
const JsonViewer: React.FC<{ url: string; title: string }> = ({ url, title }) => {
  const [content, setContent] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get('/resource', { params: { url } })
      .then(res => setContent(res.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [url]);

  if (loading) return <div className="p-4 text-gray-400">加载文本内容中...</div>;

  return (
    <div className="bg-white p-6 rounded-lg shadow border border-gray-100">
      <h4 className="text-sm font-bold text-gray-400 uppercase mb-4">{title}</h4>
      <div className="prose max-w-none whitespace-pre-wrap font-serif text-gray-800 leading-relaxed">
        {typeof content === 'string' ? content : JSON.stringify(content, null, 2)}
      </div>
    </div>
  );
};

const ResourceViewer: React.FC<Props> = ({ segmentId, urls }) => {
  if (!urls || urls.length === 0) return <div className="text-gray-400 text-center py-10">暂无资源生成</div>;

  const type = SEGMENT_TYPE_MAP[segmentId];

  if (type === 'story_json') {
    return <div className="space-y-4">{urls.map((url, i) => <JsonViewer key={i} url={url} title="生成故事 (JSON)" />)}</div>;
  }

  if (type === 'split_json') {
    return <div className="space-y-4">{urls.map((url, i) => <JsonViewer key={i} url={url} title="分镜脚本 (JSON)" />)}</div>;
  }

  if (type === 'image') {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {urls.map((url, i) => <SecureImage key={i} src={url} />)}
      </div>
    );
  }

  if (type === 'audio') {
    return (
      <div className="space-y-2">
        {urls.map((url, i) => <SecureAudio key={i} src={url} />)}
      </div>
    );
  }

  if (type === 'video') {
    return (
      <div className="space-y-4">
        {urls.map((url, i) => <SecureVideo key={i} src={url} />)}
      </div>
    );
  }

  return <div>未知资源类型</div>;
};

export default ResourceViewer;