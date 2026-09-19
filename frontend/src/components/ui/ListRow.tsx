import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface Props {
  /** Left column, e.g. a card's short id. */
  lead?: ReactNode;
  /** Right-aligned trailing text. */
  trail?: ReactNode;
  onClick?: () => void;
  children: ReactNode;
}

/** One row of a list: lead, content, trailing value. Clickable when `onClick` is given. */
export function ListRow({ lead, trail, onClick, children }: Props) {
  const Element = onClick ? 'button' : 'div';
  return (
    <Element
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-3 rounded-control border border-line bg-surface-2 px-3.5 py-2 text-left',
        onClick && 'hover:border-accent-2',
      )}
    >
      {lead !== undefined && (
        <span className="min-w-11 text-[13px] text-fg-faint tabular-nums">{lead}</span>
      )}
      {children}
      {trail !== undefined && <span className="ml-auto text-xs text-fg-dim">{trail}</span>}
    </Element>
  );
}

export function ListRows({ children }: { children: ReactNode }) {
  return <div className="grid gap-1.5">{children}</div>;
}
