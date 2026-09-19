import type { Budget, JobStatus } from '@/api/types';
import { EmptyState } from '@/components/ui/EmptyState';
import { ListRow } from '@/components/ui/ListRow';
import { Panel, PanelLabel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Note } from '@/components/ui/typography';

/** What is left of each metered allowance over its rolling window. */
export function BudgetPanels({ budgets }: { budgets: Budget[] }) {
  if (!budgets.length) return <EmptyState>Sin fuentes con límite configuradas.</EmptyState>;

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3">
      {budgets.map((budget) => {
        const used = budget.limit ? (100 * budget.used) / budget.limit : 0;
        return (
          <Panel key={budget.provider}>
            <PanelLabel>{budget.provider}</PanelLabel>
            <div className="mt-1 text-xl">
              <strong>{budget.remaining}</strong> disponibles
            </div>
            <ProgressBar
              value={budget.used}
              max={budget.limit}
              tone={used >= 90 ? 'bad' : used >= 70 ? 'warn' : 'good'}
            />
            <Note>
              {budget.used} de {budget.limit} usadas en las últimas {budget.window_hours} h. Las más
              viejas van saliendo solas.
            </Note>
          </Panel>
        );
      })}
    </div>
  );
}

const STATUS_LABELS: Record<JobStatus['status'], string> = {
  idle: '',
  running: 'En curso',
  done: 'Terminada',
  failed: 'Falló',
};

/** The last background job run in this server session. */
export function JobState({ job }: { job: JobStatus }) {
  if (job.status === 'idle') {
    return <EmptyState>Sin tareas ejecutadas en esta sesión.</EmptyState>;
  }

  return (
    <ListRow
      lead={job.name ?? ''}
      trail={
        job.error ? (
          <span className="text-bad">{job.error}</span>
        ) : job.result ? (
          JSON.stringify(job.result)
        ) : (
          ''
        )
      }
    >
      <span>
        {STATUS_LABELS[job.status]}
        {job.started_at && ` · ${job.started_at}`}
      </span>
    </ListRow>
  );
}
