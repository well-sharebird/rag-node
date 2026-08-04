/**
 * 文档处理进度追踪 Hook
 * 轮询文档处理进度直到完成
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchApi } from '@/lib/api-client';

export interface DocumentProgress {
  doc_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number; // 0-100
  current_stage: string | null;
  chunk_count: number | null;
  error_message: string | null;
  uploaded_at: string;
  processed_at: string | null;
}

export function useDocumentProgress(docId: string | null, enabled: boolean = true) {
  const [progress, setProgress] = useState<DocumentProgress | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchProgress = useCallback(async () => {
    if (!docId) return;

    try {
      const data = await fetchApi<DocumentProgress>(`/api/v1/documents/${docId}/progress`);
      setProgress(data);
      setError(null);

      // 如果处理完成或失败，停止轮询
      if (data.status === 'completed' || data.status === 'failed') {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch (err: any) {
      setError(err.message || '获取进度失败');
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    if (!enabled || !docId) return;

    setLoading(true);
    fetchProgress();

    // 每 2 秒轮询一次
    intervalRef.current = setInterval(fetchProgress, 2000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [docId, enabled, fetchProgress]);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  return { progress, loading, error, refetch: fetchProgress, stop };
}
