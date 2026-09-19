import { createContext, use, useCallback, useMemo, useRef, useState, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface ToastState {
  message: string;
  isError: boolean;
}

type ShowToast = (message: string, isError?: boolean) => void;

const ToastContext = createContext<ShowToast | null>(null);

const VISIBLE_MS = 3200;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const show = useCallback<ShowToast>((message, isError = false) => {
    window.clearTimeout(timer.current);
    setToast({ message, isError });
    timer.current = window.setTimeout(() => setToast(null), VISIBLE_MS);
  }, []);

  const value = useMemo(() => show, [show]);

  return (
    <ToastContext value={value}>
      {children}
      {toast && (
        <div
          role="status"
          className={cn(
            'fixed bottom-7 left-1/2 z-200 -translate-x-1/2 rounded-full border bg-surface-3 px-4.5 py-2.5 text-sm shadow-pop',
            toast.isError ? 'border-bad text-bad' : 'border-line text-fg',
          )}
        >
          {toast.message}
        </div>
      )}
    </ToastContext>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ShowToast {
  const show = use(ToastContext);
  if (!show) throw new Error('useToast must be used inside <ToastProvider>');
  return show;
}
