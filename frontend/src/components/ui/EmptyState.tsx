import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

/** Centered, muted text: "loading", "nothing here", or an error. */
export function EmptyState({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('text-center text-fg-faint', className)}>{children}</div>;
}
