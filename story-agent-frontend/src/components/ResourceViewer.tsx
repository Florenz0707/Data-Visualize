import React, { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { SEGMENT_TYPE_MAP } from '../types';

interface Props {
  segmentId: number;
  urls: string[];
}

const SecureImage: React.FC<{ src: string }> = ({ src }) => {
  const [objectUrl, setObjectUrl] = useState<string>('');

  useEffect(() => {
    let active = true;
    let currentUrl = '';

    const fetchImage = async () => {
      try {
        const response = await api.get(src, { responseType: 'blob' });
        if (active) {
          const url = URL.createObjectURL(response.data);
          currentUrl = url;
          setObjectUrl(url);
        }
      } catch (e) {
        console.error("Image load failed", e);
      }
    };
    
    fetchImage();

    return () => {
      active = false;
      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
      }
    };
  }, [src]);

  if (!objectUrl) return <div className="w-full h-48 bg-gray-200 animate-pulse rounded"></div>;
  return <img src={objectUrl} alt="Generated" className="w-full h-auto rounded shadow hover:shadow-lg transition" />;
};

const JsonViewer: React.FC<{ url: string; title: string }> = ({ url, title }) => {
  const [content, setContent] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(url)
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
        {urls.map((url, i) => (
          <div key={i} className="bg-white p-3 rounded shadow flex items-center">
             <audio controls className="w-full h-10">
                 <source src={`/api${url}`} />
             </audio>
          </div>
        ))}
      </div>
    );
  }

  if (type === 'video') {
    return (
      <div className="space-y-4">
        {urls.map((url, i) => (
          <video key={i} controls className="w-full rounded-lg shadow-xl bg-black aspect-video">
             <source src={`/api${url}`} />
          </video>
        ))}
      </div>
    );
  }

  return <div>未知资源类型</div>;
};

export default ResourceViewer;