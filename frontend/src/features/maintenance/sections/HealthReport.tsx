import { useQuery } from '@tanstack/react-query';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { HealthFinding } from '@/api/types';
import { EmptyState } from '@/components/ui/EmptyState';
import { Note } from '@/components/ui/typography';
import { cn } from '@/lib/cn';

const LEVEL_EDGE: Record<HealthFinding['level'], string> = {
  error: 'border-bad',
  warning: 'border-warn',
  info: 'border-fg-faint',
};

const MAX_DETAILS = 6;

/** Vocabulary mismatches the backend found: things that raise no error and skew numbers. */
export function HealthReport() {
  const { data, isPending } = useQuery({ queryKey: queryKeys.health, queryFn: api.health });

  if (isPending) return <Note>Comprobando…</Note>;
  if (!data) return null;
  if (!data.findings.length) {
    return (
      <EmptyState>
        Sin desajustes. Grados, rarezas, números y fechas de set son consistentes.
      </EmptyState>
    );
  }

  return (
    <ul className="mt-1.5 grid gap-1.5">
      {data.findings.map((finding) => (
        <li
          key={finding.message}
          className={cn(
            'rounded-r-md border-l-[3px] bg-gray-500/10 px-2.5 py-1.5 text-[13px]',
            LEVEL_EDGE[finding.level],
          )}
        >
          {finding.message}
          {finding.detail.length > 0 && (
            <div className="mt-0.5 text-xs text-fg-dim">
              {finding.detail.slice(0, MAX_DETAILS).join(' · ')}
              {finding.detail.length > MAX_DETAILS && ` … +${finding.detail.length - MAX_DETAILS}`}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
