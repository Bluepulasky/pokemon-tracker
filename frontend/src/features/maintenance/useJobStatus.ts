import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { useToast } from '@/context/ToastContext';

const POLL_MS = 3000;

/**
 * The background job's state, polled while it runs, with a toast when it ends.
 * Polled rather than streamed: a job lasts minutes and there is one at a time.
 */
export function useJobStatus() {
  const toast = useToast();
  const query = useQuery({
    queryKey: queryKeys.jobStatus,
    queryFn: api.jobStatus,
    refetchInterval: (latest) => (latest.state.data?.status === 'running' ? POLL_MS : false),
    // A job outlasts the user's attention: keep polling with the tab in the background.
    refetchIntervalInBackground: true,
  });

  const status = query.data?.status;
  const error = query.data?.error;
  const previous = useRef(status);
  useEffect(() => {
    if (previous.current === 'running' && status && status !== 'running') {
      toast(status === 'done' ? 'Tarea terminada' : `Tarea fallida: ${error}`, status !== 'done');
    }
    previous.current = status;
  }, [status, error, toast]);

  return query;
}
