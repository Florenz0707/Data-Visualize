import React, { useEffect, useState, useMemo } from 'react';
import { api, taskApi } from '../lib/api';
import { SEGMENT_TYPE_MAP, VIDEOGEN_SEGMENT_TYPE_MAP } from '../types';

interface Props {
  taskId: string; 
  segmentId: number;
  urls: string[];
  taskMode?: 'story' | 'videogen';
  onResourceUpdate?: () => void; 
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
  return data && Array.isArray(data.pages) && data.pages.length > 0;
}

const useSecureResource = (url: string) => {
  const [objectUrl, setObjectUrl] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let currentUrl = '';
    const fetchResource = async () => {
      try {
        setLoading(true);
        const response = await api.get('/resource', { params: { url }, responseType: 'blob' });
        if (active) {
          const blobUrl = URL.createObjectURL(response.data);
          currentUrl = blobUrl;
          setObjectUrl(blobUrl);
        }
      } catch (e) {
        console.error("Resource load failed", e);
      } finally {
        if (active) setLoading(false);
      }
    };
    if (url) fetchResource();
    return () => { active = false; if (currentUrl) URL.revokeObjectURL(currentUrl); };
  }, [url]);

  return { objectUrl, loading };
};

// 音频播放小组件
const InlineAudioPlayer: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);
  if (loading) return <span className="text-xs text-gray-400 ml-2">加载音频...</span>;
  return (
    <div className="mt-2">
      <audio controls className="w-full h-8" src={objectUrl} />
    </div>
  );
};

const SecureImage: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);
  if (loading) return <div className="w-full h-48 bg-gray-100 animate-pulse rounded flex items-center justify-center text-gray-400">加载图片...</div>;
  return <img src={objectUrl} alt="Generated" className="w-full h-auto rounded shadow hover:shadow-lg transition" />;
};

const SecureVideo: React.FC<{ src: string }> = ({ src }) => {
  const { objectUrl, loading } = useSecureResource(src);
  if (loading) return <div className="w-full aspect-video bg-gray-800 rounded-lg animate-pulse flex items-center justify-center text-gray-400">加载视频中...</div>;
  return <video controls className="w-full rounded-lg shadow-xl bg-black aspect-video" src={objectUrl} />;
};

// --- 可视化/编辑组件 ---

interface StoryboardProps {
  data: StoryData;
  mode: 'read' | 'edit-story' | 'edit-split' | 'speech';
  onSave?: (newData: StoryData) => Promise<void>;
  audioUrls?: string[]; 
}

const StoryboardViewer: React.FC<StoryboardProps> = ({ data, mode, onSave, audioUrls }) => {
  const [localData, setLocalData] = useState<StoryData>(data);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => { setLocalData(data); }, [data]);

  const audioMap = useMemo(() => {
    const map = new Map<string, string>();
    if (!audioUrls) return map;

    audioUrls.forEach(url => {
      const filename = url.split('/').pop() || '';
      const match = filename.match(/s(\d+)_(\d+)\.wav$/);
      if (match) {
        const sceneIdx = match[1];
        const segIdx = match[2];
        const key = `${sceneIdx}_${segIdx}`;
        map.set(key, url);
      }
    });
    return map;
  }, [audioUrls]);

  const handleSave = async () => {
    if (!onSave) return;
    setIsSaving(true);
    try {
      await onSave(localData);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col min-h-full">
      {(mode === 'edit-story' || mode === 'edit-split') && (
        <div className="sticky top-0 z-30 bg-gray-50/95 backdrop-blur-md border-b border-gray-200 py-4 px-8 flex justify-between items-center shadow-sm">
          <div className="flex items-center gap-2 text-gray-500">
            <span className="text-lg">✏️</span>
            <span className="font-bold text-sm uppercase tracking-wider">
              {mode === 'edit-story' ? '编辑故事内容' : '编辑分镜脚本'}
            </span>
          </div>
          <button 
            onClick={handleSave} 
            disabled={isSaving}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg shadow-md hover:bg-blue-700 disabled:opacity-50 transition-all flex items-center gap-2 font-medium text-sm"
          >
            {isSaving ? (
              <>
                <span className="animate-spin">⟳</span> 保存中...
              </>
            ) : (
              <>💾 保存并重做后续</>
            )}
          </button>
        </div>
      )}

      <div className="p-8 grid grid-cols-1 gap-8">
        {localData.pages.map((page, index) => {
          const segments = localData.segmented_pages?.[index] || [];
          const sceneNum = index + 1;

          return (
            <div key={index} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-200">
              <div className="bg-gray-50 px-5 py-3 border-b border-gray-100 flex justify-between items-center">
                <span className="bg-blue-100 text-blue-700 text-xs font-bold px-2 py-1 rounded">SCENE {sceneNum}</span>
              </div>

              <div className="p-6 flex flex-col gap-6">
                <div>
                  <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Story Context</h4>
                  {mode === 'edit-story' ? (
                    <textarea
                      className="w-full border border-blue-300 rounded p-3 text-lg font-serif focus:ring-2 focus:ring-blue-500 outline-none"
                      rows={4}
                      value={page.story}
                      onChange={(e) => {
                        const newPages = [...localData.pages];
                        newPages[index] = { ...newPages[index], story: e.target.value };
                        setLocalData({ ...localData, pages: newPages });
                      }}
                    />
                  ) : (
                    <p className="text-gray-800 text-lg leading-relaxed font-serif">{page.story}</p>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch">
                  <div className="flex flex-col h-full">
                    {page.image_prompt ? (
                      <div className="bg-purple-50 p-5 rounded-lg border border-purple-100 h-full flex flex-col min-h-[160px]">
                        <h4 className="text-xs font-bold text-purple-600 uppercase tracking-wider mb-3 flex items-center gap-2 shrink-0">
                          <span>🎨</span> Image Prompt
                        </h4>
                        <p className="text-gray-600 text-sm italic leading-relaxed flex-1">
                          {page.image_prompt}
                        </p>
                      </div>
                    ) : (
                      <div className="bg-gray-50 p-5 rounded-lg border border-gray-200 border-dashed flex items-center justify-center h-full min-h-[160px]">
                        <span className="text-gray-400 text-sm italic">提示词将在 Image 阶段生成...</span>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col h-full">
                    <div className="bg-green-50 p-5 rounded-lg border border-green-100 h-full flex flex-col min-h-[160px]">
                      <h4 className="text-xs font-bold text-green-600 uppercase tracking-wider mb-3 shrink-0 flex items-center gap-2">
                        {mode === 'speech' ? <span>🎙️ Speech & Audio</span> : <span>📝 Split Segments</span>}
                      </h4>

                      <div className="flex-1">
                        {mode === 'edit-split' ? (
                          <textarea
                            className="w-full h-full min-h-[120px] border border-green-300 rounded p-3 text-sm font-mono bg-white focus:ring-2 focus:ring-green-500 outline-none resize-y"
                            value={segments.join('\n')}
                            placeholder="每行一句"
                            onChange={(e) => {
                              const newSegPages = [...(localData.segmented_pages || [])];
                              while (newSegPages.length <= index) newSegPages.push([]);
                              newSegPages[index] = e.target.value.split('\n').filter(s => s.trim());
                              setLocalData({ ...localData, segmented_pages: newSegPages });
                            }}
                          />
                        ) : (
                          <ul className="space-y-3">
                            {segments.length > 0 ? segments.map((seg, i) => {
                              const segNum = i + 1;
                              const audioKey = `${sceneNum}_${segNum}`;
                              const audioUrl = mode === 'speech' ? audioMap.get(audioKey) : null;
                              
                              return (
                                <li key={i} className="text-sm text-gray-700 bg-white/50 p-2 rounded border border-green-100/50">
                                  <div className="flex items-start gap-2">
                                    <span className="text-green-500 mt-0.5">•</span>
                                    <span className="font-medium leading-relaxed">{seg}</span>
                                  </div>
                                  {audioUrl && <InlineAudioPlayer src={audioUrl} />}
                                </li>
                              );
                            }) : (
                              <li className="text-gray-400 text-sm italic text-center py-4">暂无分段台词</li>
                            )}
                          </ul>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// --- 主容器 ---

const ResourceViewer: React.FC<Props> = ({ taskId, segmentId, urls, taskMode = 'story', onResourceUpdate }) => {
  const [jsonContent, setJsonContent] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [speechContextData, setSpeechContextData] = useState<any>(null);

  useEffect(() => {
    // @ts-ignore
    const type = taskMode === 'videogen' ? VIDEOGEN_SEGMENT_TYPE_MAP[segmentId] : SEGMENT_TYPE_MAP[segmentId];
    
    if (type === 'story_json' || type === 'split_json') {
      if (urls[0]) {
        setLoading(true);
        api.get('/resource', { params: { url: urls[0] } })
          .then(res => setJsonContent(res.data))
          .catch(console.error)
          .finally(() => setLoading(false));
      }
    }

    if (type === 'audio') {
      setLoading(true);
      taskApi.getResource(taskId, 3)
        .then(async (res) => {
           if (res.data.urls && res.data.urls[0]) {
             const jsonRes = await api.get('/resource', { params: { url: res.data.urls[0] } });
             setSpeechContextData(jsonRes.data);
           }
        })
        .catch(err => console.warn("无法获取 Speech 的文本上下文", err))
        .finally(() => setLoading(false));
    }

  }, [taskId, segmentId, urls, taskMode]);

  const handleUpdateResource = async (newData: StoryData) => {
    try {
      let payload: any = {};
      if (segmentId === 1) {
        payload = { pages: newData.pages.map(p => ({ story: p.story })) };
      } else if (segmentId === 3) {
        payload = { segmented_pages: newData.segmented_pages };
      }

      await taskApi.updateResource(taskId, segmentId, payload);
      alert("更新成功，后续步骤已重置");
      if (onResourceUpdate) onResourceUpdate();
    } catch (e) {
      console.error("Update failed", e);
      alert("更新失败，请重试");
    }
  };

  if (!urls || urls.length === 0) return <div className="p-8 text-gray-400 text-center py-10">暂无资源</div>;

  // @ts-ignore
  const type = taskMode === 'videogen' ? (VIDEOGEN_SEGMENT_TYPE_MAP[segmentId] || 'unknown') : SEGMENT_TYPE_MAP[segmentId];

  if (loading) return <div className="p-10 text-center text-gray-400">加载资源中...</div>;

  if (type === 'story_json' && isStoryData(jsonContent)) {
    return <StoryboardViewer data={jsonContent} mode="edit-story" onSave={handleUpdateResource} />;
  }

  if (type === 'split_json' && isStoryData(jsonContent)) {
    return <StoryboardViewer data={jsonContent} mode="edit-split" onSave={handleUpdateResource} />;
  }

  if (type === 'audio' && isStoryData(speechContextData)) {
    return <StoryboardViewer data={speechContextData} mode="speech" audioUrls={urls} />;
  }

  return (
    <div className="p-8">
      {type === 'audio' && (
        <div className="space-y-2">{urls.map((url, i) => <InlineAudioPlayer key={i} src={url} />)}</div>
      )}

      {type === 'image' && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">{urls.map((url, i) => <SecureImage key={i} src={url} />)}</div>
      )}

      {type === 'video' && (
        <div className="space-y-4">{urls.map((url, i) => <SecureVideo key={i} src={url} />)}</div>
      )}
      
      {/* Fallback for unknown types */}
      {![ 'story_json', 'split_json', 'audio', 'image', 'video'].includes(type) && (
        <div>未知资源类型: {type}</div>
      )}
    </div>
  );
};

export default ResourceViewer;