import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

/** The boxed strip of filters above a grid or list. */
export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        'mt-4 mb-5 flex flex-wrap items-center gap-2 rounded-card border border-line bg-surface-2 p-3 text-sm',
        className,
      )}
    >
      {children}
    </div>
  );
}
