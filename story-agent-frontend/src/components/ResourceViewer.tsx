import React, { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { SEGMENT_TYPE_MAP, VIDEOGEN_SEGMENT_TYPE_MAP } from '../types';

interface Props {
  segmentId: number;
  urls: string[];
  taskMode?: 'story' | 'videogen';
}

interface StoryPage {
  story: string;
  image_prompt?: string;
}

interface StoryData {
  pages: StoryPage[];
  segmented_pages?: string[][];
}

function isStoryData(data: any): data is StoryData {
  return data && Array.isArray(data.pages) && data.pages.length > 0 && typeof data.pages[0].story === 'string';
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

const SecureImage: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);
  if (loading) return <div className="w-full h-48 bg-gray-100 animate-pulse rounded flex items-center justify-center text-gray-400">加载图片...</div>;
  if (!objectUrl) return <div className="w-full h-48 bg-gray-100 rounded flex items-center justify-center text-gray-400">图片加载失败</div>;
  return <img src={objectUrl} alt="Generated" className="w-full h-auto rounded shadow hover:shadow-lg transition" />;
};

const SecureAudio: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);
  if (loading) return <div className="p-4 bg-gray-50 rounded animate-pulse text-sm text-gray-500">加载音频中...</div>;
  return (
    <div className="bg-white p-3 rounded shadow flex items-center border border-gray-100">
      <audio controls className="w-full h-10" src={objectUrl}>您的浏览器不支持音频播放</audio>
    </div>
  );
};

const SecureVideo: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);
  if (loading) return <div className="w-full aspect-video bg-gray-800 rounded-lg animate-pulse flex items-center justify-center text-gray-400">加载视频中...</div>;
  return (
    <video controls className="w-full rounded-lg shadow-xl bg-black aspect-video" src={objectUrl}>您的浏览器不支持视频播放</video>
  );
};

const StoryboardViewer: React.FC<{ data: StoryData }> = ({ data }) => {
  const { pages, segmented_pages } = data;

  return (
    <div className="grid grid-cols-1 gap-6">
      {pages.map((page, index) => {
        // 获取对应的分段台词（如果存在）
        const segments = segmented_pages && segmented_pages[index];

        return (
          <div key={index} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-all duration-200">
            {/* 顶部：场景号 */}
            <div className="bg-gray-50 px-5 py-3 border-b border-gray-100 flex justify-between items-center">
              <div className="flex items-center gap-2">
                <span className="bg-blue-100 text-blue-700 text-xs font-bold px-2 py-1 rounded">SCENE {index + 1}</span>
              </div>
            </div>

            <div className="p-5 flex flex-col gap-5">
              {/* 1. 故事文本 Story */}
              <div>
                <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Story Context</h4>
                <p className="text-gray-800 text-lg leading-relaxed font-serif">{page.story}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* 2. 图像提示词 Image Prompt (修正：增加存在性判断) */}
                {page.image_prompt ? (
                  <div className="bg-purple-50 p-4 rounded-lg border border-purple-100">
                    <h4 className="text-xs font-bold text-purple-600 uppercase tracking-wider mb-2 flex items-center gap-1">
                      <span>🎨</span> Image Prompt
                    </h4>
                    <p className="text-gray-600 text-sm italic leading-relaxed">
                      {page.image_prompt}
                    </p>
                  </div>
                ) : (
                  <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 border-dashed flex items-center justify-center">
                    <span className="text-gray-400 text-sm italic">提示词将在 Image 阶段生成...</span>
                  </div>
                )}

                {/* 3. 分段台词/语音文本 Speech Segments (如果有) */}
                {segments && segments.length > 0 ? (
                  <div className="bg-green-50 p-4 rounded-lg border border-green-100">
                    <h4 className="text-xs font-bold text-green-600 uppercase tracking-wider mb-2 flex items-center gap-1">
                      <span>🎙️</span> Speech Segments
                    </h4>
                    <ul className="space-y-1.5">
                      {segments.map((seg, i) => (
                        <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                          <span className="text-green-400 mt-1">•</span>
                          <span>{seg}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                   /* 占位，保持布局平衡，或者显示等待生成 */
                   <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 border-dashed flex items-center justify-center text-gray-400 text-sm italic">
                      分镜台词将在 Split 阶段生成...
                   </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

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

  if (loading) return <div className="p-4 text-gray-400 animate-pulse">正在解析脚本内容...</div>;

  if (isStoryData(content)) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
           <h4 className="text-sm font-bold text-gray-500 uppercase">{title}</h4>
           <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">VISUAL MODE</span>
        </div>
        <StoryboardViewer data={content} />
      </div>
    );
  }

  return (
    <div className="bg-white p-6 rounded-lg shadow border border-gray-100">
      <h4 className="text-sm font-bold text-gray-400 uppercase mb-4">{title} (Raw)</h4>
      <div className="prose max-w-none whitespace-pre-wrap font-serif text-gray-800 leading-relaxed font-mono text-sm">
        {typeof content === 'string' ? content : JSON.stringify(content, null, 2)}
      </div>
    </div>
  );
};

const ResourceViewer: React.FC<Props> = ({ segmentId, urls, taskMode = 'story' }) => {
  if (!urls || urls.length === 0) return <div className="text-gray-400 text-center py-10">暂无资源生成</div>;

  let type: string;
  if (taskMode === 'videogen') {
    type = VIDEOGEN_SEGMENT_TYPE_MAP[segmentId] || 'unknown';
  } else {
    type = SEGMENT_TYPE_MAP[segmentId];
  }

  if (type === 'story_json') {
    return <div className="space-y-4">{urls.map((url, i) => <JsonViewer key={i} url={url} title="生成故事脚本" />)}</div>;
  }

  if (type === 'split_json') {
    return <div className="space-y-4">{urls.map((url, i) => <JsonViewer key={i} url={url} title="分镜台词脚本" />)}</div>;
  }

  if (type === 'image') {
    return <div className="grid grid-cols-2 md:grid-cols-3 gap-4">{urls.map((url, i) => <SecureImage key={i} src={url} />)}</div>;
  }

  if (type === 'audio') {
    return <div className="space-y-2">{urls.map((url, i) => <SecureAudio key={i} src={url} />)}</div>;
  }

  if (type === 'video') {
    return <div className="space-y-4">{urls.map((url, i) => <SecureVideo key={i} src={url} />)}</div>;
  }

  return <div>未知资源类型: {type}</div>;
};

export default ResourceViewer;