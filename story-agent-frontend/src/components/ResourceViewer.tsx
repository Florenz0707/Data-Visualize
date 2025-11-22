import React, { useEffect, useState, useMemo, useRef } from 'react';
import { api, taskApi } from '../lib/api';
import { SEGMENT_TYPE_MAP, VIDEOGEN_SEGMENT_TYPE_MAP } from '../types';

export type FetchFileFn = (url: string, type: 'blob' | 'json', onProgress?: (percent: number) => void) => Promise<any>;
export type FetchSegmentResourcesFn = (segId: number) => Promise<string[]>;

interface Props {
  taskId: string; 
  segmentId: number;
  urls: string[];
  taskMode?: 'story' | 'videogen';
  completedSegId: number;
  onResourceUpdate?: () => void; 
  fetchFile: FetchFileFn; 
  fetchSegmentResources?: FetchSegmentResourcesFn;
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

const useSecureResource = (url: string, fetchFile: FetchFileFn) => {
  const [objectUrl, setObjectUrl] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState(0); 
  const [error, setError] = useState<string | null>(null); 
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    let currentUrl = '';
    
    const fetchResource = async () => {
      try {
        setLoading(true);
        setProgress(0);
        setError(null);

        const blobData = await fetchFile(url, 'blob', (percent) => {
          if (mounted.current) setProgress(percent);
        });

        if (mounted.current) {
          const blobUrl = URL.createObjectURL(blobData);
          currentUrl = blobUrl;
          setObjectUrl(blobUrl);
        }
      } catch (e: any) {
        if (mounted.current) {
           if (e.response?.data instanceof Blob) {
             setError("资源加载失败");
          } else {
            setError("网络请求失败");
          }
        }
      } finally {
        if (mounted.current) setLoading(false);
      }
    };

    if (url) fetchResource();
    
    return () => { 
      mounted.current = false; 
      if (currentUrl) URL.revokeObjectURL(currentUrl); 
    };
  }, [url, fetchFile]);

  return { objectUrl, loading, progress, error };
};

const InlineAudioPlayer: React.FC<{ src: string; fetchFile: FetchFileFn }> = ({ src, fetchFile }) => {
  const { objectUrl, loading } = useSecureResource(src, fetchFile);
  if (loading) return <span className="text-xs text-gray-400 ml-2">加载音频...</span>;
  return (
    <div className="mt-2">
      <audio controls className="w-full h-8" src={objectUrl} />
    </div>
  );
};

const SecureImage: React.FC<{ src: string; fetchFile: FetchFileFn }> = ({ src, fetchFile }) => {
  const { objectUrl, loading } = useSecureResource(src, fetchFile);
  if (loading) return (
    <div className="w-full aspect-video bg-purple-100/50 animate-pulse rounded flex items-center justify-center text-purple-300 text-xs">
      加载图片...
    </div>
  );
  if (!objectUrl) return null;
  return <img src={objectUrl} alt="Generated" className="w-full h-auto rounded shadow-sm border border-purple-100 hover:shadow-md transition" />;
};

const SecureVideo: React.FC<{ src: string; fetchFile: FetchFileFn }> = ({ src, fetchFile }) => {
  const { objectUrl, loading, progress, error } = useSecureResource(src, fetchFile);

  if (loading) return (
    <div className="w-full aspect-video bg-gray-900 rounded-lg flex flex-col items-center justify-center text-gray-400 space-y-3">
      <div className="w-10 h-10 border-2 border-gray-600 border-t-blue-500 rounded-full animate-spin"></div>
      <div className="text-sm font-medium">视频加载中 {progress}%</div>
      <div className="w-1/2 h-1 bg-gray-700 rounded-full overflow-hidden">
        <div className="h-full bg-blue-500 transition-all duration-300" style={{ width: `${progress}%` }}></div>
      </div>
    </div>
  );

  if (error) return (
    <div className="w-full aspect-video bg-gray-100 rounded-lg flex flex-col items-center justify-center text-red-400 border border-red-200">
      <span className="text-2xl mb-2">⚠️</span>
      <span>{error}</span>
      <span className="text-xs text-gray-400 mt-1">无法播放此视频</span>
    </div>
  );

  return (
    <video 
      controls 
      className="w-full rounded-lg shadow-xl bg-black aspect-video" 
      src={objectUrl} 
      playsInline
    >
      您的浏览器不支持视频播放
    </video>
  );
};

interface StoryboardProps {
  data: StoryData;
  mode: 'read' | 'edit-story' | 'edit-split' | 'speech';
  onSave?: (newData: StoryData) => Promise<void>;
  audioUrls?: string[]; 
  imageUrls?: string[];
  fetchFile: FetchFileFn; 
}

const StoryboardViewer: React.FC<StoryboardProps> = ({ data, mode, onSave, audioUrls, imageUrls, fetchFile }) => {
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
          const relatedImageUrl = imageUrls && imageUrls[index];

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
                    <div className="bg-purple-50 p-5 rounded-lg border border-purple-100 h-full flex flex-col min-h-[200px]">
                      <h4 className="text-xs font-bold text-purple-600 uppercase tracking-wider mb-3 flex items-center gap-2 shrink-0">
                        <span>🎨</span> Image Prompt
                      </h4>
                      
                      {page.image_prompt ? (
                        <p className="text-gray-600 text-sm italic leading-relaxed mb-4">
                          {page.image_prompt}
                        </p>
                      ) : (
                        <div className="text-gray-400 text-sm italic border border-purple-200 border-dashed p-2 rounded mb-4 text-center">
                           等待生成提示词...
                        </div>
                      )}

                      <div className="mt-auto">
                        {relatedImageUrl ? (
                          <div className="overflow-hidden rounded-md border border-purple-200/50 shadow-sm bg-white">
                            <SecureImage src={relatedImageUrl} fetchFile={fetchFile} />
                          </div>
                        ) : (
                          page.image_prompt && (
                            <div className="w-full aspect-video bg-purple-100/30 border border-purple-200 border-dashed rounded-md flex items-center justify-center text-purple-300 text-xs">
                              图片等待生成...
                            </div>
                          )
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-col h-full">
                    <div className="bg-green-50 p-5 rounded-lg border border-green-100 h-full flex flex-col min-h-[200px]">
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
                                  {audioUrl && <InlineAudioPlayer src={audioUrl} fetchFile={fetchFile} />}
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

const ResourceViewer: React.FC<Props> = ({ 
  taskId, 
  segmentId, 
  urls, 
  taskMode = 'story', 
  onResourceUpdate, 
  fetchFile, 
  fetchSegmentResources,
  completedSegId 
}) => {
  const [jsonContent, setJsonContent] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [speechContextData, setSpeechContextData] = useState<any>(null);
  const [images, setImages] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadError(null);
    
    // @ts-ignore
    const type = taskMode === 'videogen' ? VIDEOGEN_SEGMENT_TYPE_MAP[segmentId] : SEGMENT_TYPE_MAP[segmentId];
    
    if (type === 'story_json' || type === 'split_json') {
      if (urls[0]) {
        setLoading(true);
        fetchFile(urls[0], 'json')
          .then(data => { if (active) setJsonContent(data); })
          .catch(err => { 
            console.error(err);
            if (active) setLoadError("加载故事脚本失败");
          })
          .finally(() => { if (active) setLoading(false); });
      } else {
        setLoading(false);
      }
    }

    // 加载 Speech 上下文 (Segment 3)
    if (type === 'audio' && fetchSegmentResources && completedSegId >= 3) {
      setLoading(true);
      fetchSegmentResources(3)
        .then(async (urls) => {
           if (active && urls && urls[0]) {
             const data = await fetchFile(urls[0], 'json');
             if (active) setSpeechContextData(data);
           }
        })
        .catch(err => console.warn("context fetch failed", err))
        .finally(() => { if (active) setLoading(false); });
    }

    // 加载图片资源 (Segment 2)
    if (['story_json', 'split_json', 'audio'].includes(type) && fetchSegmentResources && completedSegId >= 2) {
      fetchSegmentResources(2)
        .then(urls => {
          if (active && urls && urls.length > 0) {
            setImages(urls);
          }
        })
        .catch(() => { if (active) setImages([]); });
    } else {
      if (active) setImages([]);
    }
    
    if (!['story_json', 'split_json', 'audio'].includes(type)) {
      setLoading(false);
    }

    return () => { active = false; };
  }, [taskId, segmentId, urls, taskMode, fetchFile, fetchSegmentResources, completedSegId]);

  const handleUpdateResource = async (newData: StoryData) => {
    try {
      let payload: any = {};
      if (segmentId === 1) {
        payload = { pages: newData.pages.map(p => ({ story: p.story })) };
      } else if (segmentId === 3) {
        payload = { segmented_pages: newData.segmented_pages };
      }

      await taskApi.updateResource(taskId, segmentId, payload);
      alert("更新成功");
      if (onResourceUpdate) onResourceUpdate();
    } catch (e) {
      console.error("Update failed", e);
      alert("更新失败");
    }
  };

  if (!urls || urls.length === 0) return <div className="p-8 text-gray-400 text-center py-10">暂无资源</div>;

  // @ts-ignore
  const type = taskMode === 'videogen' ? (VIDEOGEN_SEGMENT_TYPE_MAP[segmentId] || 'unknown') : SEGMENT_TYPE_MAP[segmentId];

  if (loading) return <div className="p-10 text-center text-gray-400">加载资源中...</div>;
  
  if (loadError) return <div className="p-8 text-center text-red-400">{loadError}</div>;

  if (type === 'story_json') {
    if (isStoryData(jsonContent)) {
      return <StoryboardViewer data={jsonContent} mode="edit-story" onSave={handleUpdateResource} imageUrls={images} fetchFile={fetchFile} />;
    }
    return <div className="p-8 text-center text-gray-400">暂无故事数据</div>;
  }

  if (type === 'split_json') {
    if (isStoryData(jsonContent)) {
      return <StoryboardViewer data={jsonContent} mode="edit-split" onSave={handleUpdateResource} imageUrls={images} fetchFile={fetchFile} />;
    }
    return <div className="p-8 text-center text-gray-400">暂无分镜数据</div>;
  }

  if (type === 'audio') {
    if (isStoryData(speechContextData)) {
      return <StoryboardViewer data={speechContextData} mode="speech" audioUrls={urls} imageUrls={images} fetchFile={fetchFile} />;
    }
    return <div className="p-8 space-y-2">{urls.map((url, i) => <InlineAudioPlayer key={i} src={url} fetchFile={fetchFile} />)}</div>;
  }

  return (
    <div className="p-8">
      {type === 'image' && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">{urls.map((url, i) => <SecureImage key={i} src={url} fetchFile={fetchFile} />)}</div>
      )}

      {type === 'video' && (
        <div className="space-y-4">{urls.map((url, i) => <SecureVideo key={i} src={url} fetchFile={fetchFile} />)}</div>
      )}
      
      {![ 'story_json', 'split_json', 'audio', 'image', 'video'].includes(type) && (
        <div>未知资源类型: {type}</div>
      )}
    </div>
  );
};

export default ResourceViewer;