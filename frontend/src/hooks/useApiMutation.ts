import { useMutation, useQueryClient } from '@tanstack/react-query';

import { invalidateAppData } from '@/api/queryClient';
import { useToast } from '@/context/ToastContext';

interface Options<TData, TVars> {
  /** Toast shown on success. */
  success?: string | ((data: TData, vars: TVars) => string);
  /** Runs after the cache was invalidated. */
  onDone?: (data: TData, vars: TVars) => void;
}

/**
 * A write to the API: toasts the error if it fails; on success toasts `success`
 * and marks cached reads stale so every visible view refetches.
 */
export function useApiMutation<TVars = void, TData = unknown>(
  mutationFn: (vars: TVars) => Promise<TData>,
  { success, onDone }: Options<TData, TVars> = {},
) {
  const client = useQueryClient();
  const toast = useToast();

  return useMutation({
    mutationFn,
    onSuccess: async (data, vars) => {
      if (success) toast(typeof success === 'function' ? success(data, vars) : success);
      await invalidateAppData(client);
      onDone?.(data, vars);
    },
    onError: (error: Error) => toast(error.message, true),
  });
}
