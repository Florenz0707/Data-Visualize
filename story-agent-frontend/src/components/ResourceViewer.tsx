import React, { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { SEGMENT_TYPE_MAP } from '../types';

interface Props {
  segmentId: number;
  urls: string[];
}

// 安全图片组件：通过 Blob 加载带 Token 的图片
const SecureImage: React.FC<{ src: string }> = ({ src }) => {
  const [objectUrl, setObjectUrl] = useState<string>('');

  useEffect(() => {
    // 如果是完整URL且不是本域，可能不需要Auth，这里假设资源都需要通过 API 代理或鉴权
    // 或者后端返回的是相对路径
    const fetchImage = async () => {
      try {
        const response = await api.get(src, { responseType: 'blob' });
        const url = URL.createObjectURL(response.data);
        setObjectUrl(url);
      } catch (e) {
        console.error("Image load failed", e);
      }
    };
    fetchImage();
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  if (!objectUrl) return <div className="w-full h-48 bg-gray-200 animate-pulse rounded"></div>;
  return <img src={objectUrl} alt="Generated" className="max-w-full h-auto rounded shadow" />;
};

// 文本查看组件
const TextViewer: React.FC<{ url: string }> = ({ url }) => {
  const [content, setContent] = useState<string>('Loading text...');
  
  useEffect(() => {
    api.get(url).then(res => {
      // 假设后端返回的是 JSON 或 纯文本
      setContent(typeof res.data === 'object' ? JSON.stringify(res.data, null, 2) : res.data);
    });
  }, [url]);

  return (
    <div className="bg-white p-4 rounded border overflow-auto max-h-[60vh] whitespace-pre-wrap font-serif leading-relaxed">
      {content}
    </div>
  );
};

const ResourceViewer: React.FC<Props> = ({ segmentId, urls }) => {
  if (!urls || urls.length === 0) return <div className="text-gray-400">暂无资源生成</div>;

  const type = SEGMENT_TYPE_MAP[segmentId];

  if (type === 'text') {
    return (
      <div className="space-y-4">
        {urls.map((url, i) => <TextViewer key={i} url={url} />)}
      </div>
    );
  }

  if (type === 'image') {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {urls.map((url, i) => <SecureImage key={i} src={url} />)}
      </div>
    );
  }

  if (type === 'audio') {
    // 音频也可以用 Blob 方式，这里简化直接用 src，如果需要鉴权请参考 SecureImage 逻辑
    return (
      <div className="space-y-2">
        {urls.map((url, i) => (
          <audio key={i} controls className="w-full">
             {/* 注意：如果音频需要 Auth，不能直接这样写，需要类似 Image 的 Blob 处理 */}
             <source src={`/api${url}`} /> 
          </audio>
        ))}
      </div>
    );
  }

  if (type === 'video') {
    return (
      <div className="space-y-4">
        {urls.map((url, i) => (
          <video key={i} controls className="w-full rounded shadow-lg bg-black">
             <source src={`/api${url}`} />
          </video>
        ))}
      </div>
    );
  }

  return <div>未知资源类型</div>;
};

export default ResourceViewer;