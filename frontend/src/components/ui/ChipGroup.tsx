import { cn } from '@/lib/cn';

export interface ChipOption<T extends string> {
  value: T;
  label: string;
  title?: string;
}

interface Props<T extends string> {
  options: readonly ChipOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** `joined`: one segmented pill. `loose`: separate chips that wrap. */
  layout?: 'joined' | 'loose';
  size?: 'sm' | 'md';
  className?: string;
}

/** A single-choice row of chips. */
export function ChipGroup<T extends string>({
  options,
  value,
  onChange,
  layout = 'joined',
  size = 'sm',
  className,
}: Props<T>) {
  const joined = layout === 'joined';

  return (
    <div
      role="radiogroup"
      className={cn(
        'flex w-fit max-w-full',
        joined
          ? 'divide-x divide-line overflow-hidden rounded-full border border-line'
          : 'flex-wrap gap-1.5',
        className,
      )}
    >
      {options.map((option) => {
        const on = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={on}
            title={option.title}
            onClick={() => onChange(option.value)}
            className={cn(
              'whitespace-nowrap transition',
              size === 'md'
                ? 'px-4.5 py-2 text-sm'
                : 'px-3 py-1 text-[11px] sm:px-3.5 sm:py-1.5 sm:text-[15px]',
              !joined && 'rounded-full border border-line',
              on ? 'bg-accent font-semibold text-accent-ink' : 'bg-surface-3',
              on && !joined && 'border-accent',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
