import { cn } from '@/lib/cn';
import { ratio } from '@/lib/format';

type Tone = 'auto' | 'good' | 'warn' | 'bad';

interface Props {
  value: number;
  max: number;
  /** `auto`: accent, turning green at 100%. */
  tone?: Tone;
  className?: string;
}

const TONES: Record<Exclude<Tone, 'auto'>, string> = {
  good: 'bg-good',
  warn: 'bg-warn',
  bad: 'bg-bad',
};

export function ProgressBar({ value, max, tone = 'auto', className }: Props) {
  const percent = ratio(value, max);
  const fill = tone === 'auto' ? (percent >= 100 ? 'bg-good' : 'bg-accent') : TONES[tone];

  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn('mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface-3', className)}
    >
      <div
        className={cn('h-full rounded-full transition-[width] duration-500', fill)}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
