import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

type Corner = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
type Tone = 'accent' | 'good' | 'blue' | 'dark' | 'muted';

const CORNERS: Record<Corner, string> = {
  'top-left': 'top-1.5 left-1.5',
  'top-right': 'top-1.5 right-1.5',
  'bottom-left': 'bottom-1.5 left-1.5',
  'bottom-right': 'right-1.5 bottom-1.5',
};

const TONES: Record<Tone, string> = {
  accent: 'bg-accent/90 text-accent-ink',
  good: 'bg-good/90 text-[#04221a]',
  blue: 'bg-accent-2/90 text-white',
  dark: 'bg-surface/80 text-fg',
  muted: 'bg-surface/80 text-fg-dim text-[9px] font-semibold',
};

interface Props {
  corner: Corner;
  tone: Tone;
  title?: string;
  children: ReactNode;
}

/** A pill pinned to one corner of a card's art. */
export function CardBadge({ corner, tone, title, children }: Props) {
  return (
    <span
      title={title}
      className={cn(
        'absolute rounded-full px-1.5 py-0.5 text-[10px] leading-normal font-bold tabular-nums backdrop-blur-sm',
        CORNERS[corner],
        TONES[tone],
      )}
    >
      {children}
    </span>
  );
}
