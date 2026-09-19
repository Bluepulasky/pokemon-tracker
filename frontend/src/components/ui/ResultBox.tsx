import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface SummaryProps {
  tone: 'ok' | 'partial';
  children: ReactNode;
}

/** The one-line outcome of an import, with a green or amber edge. */
export function ResultSummary({ tone, children }: SummaryProps) {
  return (
    <div
      className={cn(
        'mt-2.5 rounded-md border-l-[3px] bg-gray-500/10 px-2.5 py-1.5 text-sm',
        tone === 'ok' ? 'border-good' : 'border-warn',
      )}
    >
      {children}
    </div>
  );
}

interface DetailProps {
  summary: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** A collapsible list of the rows behind a `ResultSummary`. */
export function ResultDetail({ summary, defaultOpen, children }: DetailProps) {
  return (
    <details open={defaultOpen} className="mt-1.5 text-[13px]">
      <summary className="text-fg-dim">{summary}</summary>
      <div className="mt-1 max-h-64 overflow-y-auto">{children}</div>
    </details>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  return <div className="mt-2.5 text-sm text-bad">{children}</div>;
}
