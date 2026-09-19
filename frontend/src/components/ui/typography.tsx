import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

type TextProps = HTMLAttributes<HTMLElement>;

export function PageTitle({ className, ...rest }: TextProps) {
  return <h1 className={cn('mb-1 text-2xl font-bold tracking-tight', className)} {...rest} />;
}

export function SectionTitle({ className, ...rest }: TextProps) {
  return (
    <h2
      className={cn(
        'mt-4 mb-3 text-xs font-semibold tracking-widest text-fg-dim uppercase',
        className,
      )}
      {...rest}
    />
  );
}

export function Subtitle({ className, ...rest }: TextProps) {
  return <p className={cn('text-sm text-fg-dim', className)} {...rest} />;
}

export function Note({ className, ...rest }: TextProps) {
  return <div className={cn('mt-2 text-xs text-fg-faint', className)} {...rest} />;
}

/** The small monospace pill used for a copy's variant, grade, language… */
export function Tag({ className, ...rest }: TextProps) {
  return (
    <span
      className={cn(
        'rounded-full border border-line bg-surface px-2 py-0.5 font-mono text-[10px] text-fg-dim',
        className,
      )}
      {...rest}
    />
  );
}
