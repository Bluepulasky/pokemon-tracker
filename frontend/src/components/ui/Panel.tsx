import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/cn';

/** The bordered surface every boxed block sits on. */
export function Panel({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('rounded-card border border-line bg-surface-2 p-4', className)} {...rest} />
  );
}

export function PanelLabel({ children }: { children: ReactNode }) {
  return <div className="text-[11px] tracking-wider text-fg-faint uppercase">{children}</div>;
}

interface StatTileProps {
  label: ReactNode;
  value: ReactNode;
  accent?: boolean;
  className?: string;
  children?: ReactNode;
}

/** A dashboard figure: small label, big value, optional extras underneath. */
export function StatTile({ label, value, accent, className, children }: StatTileProps) {
  return (
    <Panel className={cn('max-md:px-2 max-md:py-2.5', className)}>
      <div className="text-[8px] tracking-wider text-fg-faint uppercase md:text-[11px]">
        {label}
      </div>
      <div
        className={cn(
          'mt-1 text-sm font-semibold tracking-tight md:text-[25px]',
          accent && 'text-accent',
        )}
      >
        {value}
      </div>
      {children}
    </Panel>
  );
}
