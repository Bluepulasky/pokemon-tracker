import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface Props {
  name: string;
  /** Art URL; blank renders the hatched placeholder with `number` and `setCode`. */
  image: string;
  number?: string;
  setCode?: string;
  /** Not owned: the art is greyed and hatched. */
  missing?: boolean;
  /** Faded out, e.g. a card outside the collecting rule. */
  dimmed?: boolean;
  /** Thick accent frame around the art. */
  framed?: boolean;
  onClick: () => void;
  /** Badges and buttons laid over the art. */
  overlay?: ReactNode;
  /** Text under the art. */
  caption?: ReactNode;
}

/** One card in a grid: its art (or a placeholder), overlays, and an optional caption. */
export function CardTile({
  name,
  image,
  number,
  setCode,
  missing = false,
  dimmed = false,
  framed = false,
  onClick,
  overlay,
  caption,
}: Props) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === 'Enter') onClick();
      }}
      className={cn(
        'group relative rounded-control transition hover:-translate-y-0.75',
        dimmed && 'opacity-40 hover:opacity-70',
      )}
    >
      <div
        className={cn(
          'relative aspect-card overflow-hidden rounded-control bg-surface-3',
          framed ? 'border-4 border-accent' : 'border border-line',
        )}
      >
        {image ? (
          <img
            src={image}
            alt={name}
            loading="lazy"
            className={cn(
              'block size-full object-cover',
              framed && 'scale-[1.03]',
              missing &&
                'brightness-[.72] contrast-[.92] grayscale-[.75] group-hover:brightness-95 group-hover:grayscale-[.15]',
            )}
          />
        ) : (
          <CardPlaceholder number={number} setCode={setCode} />
        )}
        {missing && image && (
          <div className="pointer-events-none absolute inset-0 transition-opacity hatch-overlay group-hover:opacity-35" />
        )}
        {overlay}
      </div>
      {caption}
    </div>
  );
}

function CardPlaceholder({ number, setCode }: { number?: string; setCode?: string }) {
  return (
    <div className="flex size-full flex-col items-center justify-center gap-1 p-2 text-center hatch-solid">
      <div className="text-xl font-extrabold tracking-tight text-[#f2f5f9]">#{number ?? '?'}</div>
      <div className="text-[10px] font-semibold tracking-wider text-[#97a3b3] uppercase">
        {setCode}
      </div>
    </div>
  );
}

interface CaptionProps {
  name: string;
  detail: string;
  muted?: boolean;
}

export function CardCaption({ name, detail, muted }: CaptionProps) {
  return (
    <div className="mt-1.5 text-xs/tight">
      <span className={cn('block truncate font-medium', muted && 'text-fg-dim')}>{name}</span>
      <span className="text-fg-faint tabular-nums">{detail}</span>
    </div>
  );
}

export function CardGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
      {children}
    </div>
  );
}
