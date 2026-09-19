import { useQuery } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Dashboard, SetProgress, Snapshot } from '@/api/types';
import { SetCard, SetGrid } from '@/components/sets/SetCard';
import { AsyncView } from '@/components/ui/AsyncView';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { ListRow, ListRows } from '@/components/ui/ListRow';
import { StatTile } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Note, PageTitle, SectionTitle, Tag } from '@/components/ui/typography';
import { useCardModal } from '@/context/CardModalContext';
import { useApiMutation } from '@/hooks/useApiMutation';
import { eur, pct, shortId } from '@/lib/format';

// Chart.js is the heaviest dependency and only this page draws a chart.
const ValueChart = lazy(() =>
  import('@/components/charts/ValueChart').then((module) => ({ default: module.ValueChart })),
);

export function DashboardPage() {
  const dashboard = useQuery({ queryKey: queryKeys.dashboard, queryFn: api.dashboard });
  const history = useQuery({ queryKey: queryKeys.history, queryFn: api.history });

  return (
    <AsyncView queries={[dashboard, history]}>
      {dashboard.data && history.data && (
        <DashboardContent data={dashboard.data} snapshots={history.data.data} />
      )}
    </AsyncView>
  );
}

function DashboardContent({ data, snapshots }: { data: Dashboard; snapshots: Snapshot[] }) {
  return (
    <>
      <PageTitle>Mi colección</PageTitle>
      <Stats data={data} />

      <SectionTitle>Evolución del valor</SectionTitle>
      <Suspense fallback={<div className="h-50" />}>
        <ValueChart snapshots={snapshots} />
      </Suspense>
      {snapshots.length < 2 && <Note>El histórico se acumula con cada snapshot.</Note>}

      <SetSection title="Sets más completos" sets={data.most_complete} />
      <SetSection title="Sets con más cartas faltantes" sets={data.most_missing} />

      <SectionTitle>Cartas de mayor valor</SectionTitle>
      <TopValue rows={data.top_value} />

      <RefreshPrices lastRefresh={data.last_price_refresh} />
    </>
  );
}

function Stats({ data }: { data: Dashboard }) {
  /* Phones: a 12-column grid, four tiles on the first row and three on the second. */
  const firstRow = 'max-md:col-span-3';
  const secondRow = 'max-md:col-span-4';

  return (
    <div className="mt-2.5 grid grid-cols-12 gap-2 md:grid-cols-[repeat(auto-fit,minmax(160px,1fr))] md:gap-3">
      <StatTile
        accent
        className={firstRow}
        label="Valor estimado"
        value={eur(data.value.total_eur)}
      >
        {data.value.unpriced_items > 0 && (
          <Note>{data.value.unpriced_items} sin precio conocido</Note>
        )}
      </StatTile>
      <StatTile className={firstRow} label="Cartas únicas" value={data.unique_cards} />
      <StatTile className={firstRow} label="Cartas físicas" value={data.physical_cards} />
      <StatTile className={firstRow} label="Pokémon únicos" value={data.unique_pokemon ?? '—'} />
      <StatTile
        className={secondRow}
        label="Sets completos"
        value={
          <>
            {data.sets_complete}
            <small className="text-[13px] font-medium tracking-normal text-fg-dim">
              {' '}
              / {data.sets_total}
            </small>
          </>
        }
      >
        <ProgressBar value={data.sets_complete} max={data.sets_total} />
      </StatTile>
      <StatTile className={secondRow} label="Progreso (únicas)" value={pct(data.completion_pct)}>
        <ProgressBar value={data.owned_cards} max={data.target_cards} />
      </StatTile>
      <StatTile className={secondRow} label="Progreso (copias)" value={pct(data.copies_pct)}>
        <ProgressBar value={data.copies_held} max={data.copies_target} />
      </StatTile>
    </div>
  );
}

function SetSection({ title, sets }: { title: string; sets: SetProgress[] }) {
  return (
    <>
      <SectionTitle>{title}</SectionTitle>
      <SetGrid>
        {sets.map((set) => (
          <SetCard key={set.id} set={set} />
        ))}
      </SetGrid>
    </>
  );
}

function TopValue({ rows }: { rows: Dashboard['top_value'] }) {
  const { openFromList } = useCardModal();

  if (!rows.length) {
    return <EmptyState>Todavía no hay precios. Ejecuta una actualización de precios.</EmptyState>;
  }
  const navList = rows.map((row) => ({ id: row.card_id, name: row.name }));

  return (
    <ListRows>
      {rows.map((row, index) => (
        <ListRow
          key={`${row.card_id}-${row.variant}-${row.condition}`}
          lead={shortId(row.card_id)}
          trail={eur(row.value)}
          onClick={() => openFromList(navList, index)}
        >
          <span>{row.name}</span>
          <Tag>
            {row.variant} · {row.condition} · ×{row.quantity}
          </Tag>
        </ListRow>
      ))}
    </ListRows>
  );
}

function RefreshPrices({ lastRefresh }: { lastRefresh: string | null }) {
  const refresh = useApiMutation(api.refreshPrices, {
    success: (result) =>
      `${result.updated} precios actualizados${result.unpriced ? `, ${result.unpriced} sin datos` : ''}`,
  });

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <Button disabled={refresh.isPending} onClick={() => refresh.mutate()}>
        {refresh.isPending ? 'Actualizando…' : 'Actualizar precios ahora'}
      </Button>
      <Note className="mt-0">Última actualización: {lastRefresh ?? 'nunca'}</Note>
    </div>
  );
}
