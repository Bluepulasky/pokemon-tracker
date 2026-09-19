import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { CollectionFilters, CollectionTotals } from '@/api/types';
import { CardGrid } from '@/components/cards/CardTile';
import { AsyncView } from '@/components/ui/AsyncView';
import { ChipGroup } from '@/components/ui/ChipGroup';
import { Input, Select } from '@/components/ui/controls';
import { EmptyState } from '@/components/ui/EmptyState';
import { Toolbar } from '@/components/ui/Toolbar';
import { PageTitle, Subtitle } from '@/components/ui/typography';
import { useCardModal } from '@/context/CardModalContext';
import { useMeta } from '@/context/MetaContext';
import { useUrlFilters } from '@/hooks/useUrlFilters';

import { CollectionTile } from './CollectionTile';
import {
  FILTER_DEFAULTS,
  SELECT_FILTERS,
  selectSpecs,
  SORT_OPTIONS,
  type FilterKey,
} from './filters';

const PAGE_SIZE = 150;

const MODE_OPTIONS = [
  { value: '', label: 'En colección' },
  { value: '1', label: 'Todas las del set' },
] as const;
const HALL_OF_FAME_OPTIONS = [
  { value: '', label: 'Todas' },
  { value: '1', label: 'En Hall of Fame' },
] as const;
const REPRINT_OPTIONS = [
  { value: '', label: 'Todas las versiones', title: 'Cada reimpresión por separado' },
  {
    value: '1',
    label: 'Reprints únicos',
    title: 'Una sola entrada por carta: la impresión más vieja de cada una',
  },
] as const;

export function CollectionPage() {
  const meta = useMeta();
  const filters = useUrlFilters(FILTER_DEFAULTS);
  const { openFromList } = useCardModal();

  const showAll = filters.get('show_all') === '1';

  // What the API is asked for: every filter that is set, minus the ones that
  // only apply in a mode that is off.
  const apiFilters = useMemo(() => {
    const active: CollectionFilters = { page_size: String(PAGE_SIZE) };
    for (const key of Object.keys(FILTER_DEFAULTS) as FilterKey[]) {
      const value = filters.params.get(key) ?? FILTER_DEFAULTS[key];
      if (value) active[key] = value;
    }
    if (!showAll) delete active.unique_reprints;
    return active;
  }, [filters.params, showAll]);

  const sets = useQuery({ queryKey: queryKeys.sets, queryFn: api.sets });
  const pages = useInfiniteQuery({
    queryKey: queryKeys.collection(apiFilters),
    queryFn: ({ pageParam }) => api.collection({ ...apiFilters, page: String(pageParam) }),
    initialPageParam: 1,
    getNextPageParam: (last, all) =>
      all.reduce((count, page) => count + page.data.length, 0) < last.total
        ? all.length + 1
        : undefined,
  });

  const items = useMemo(() => pages.data?.pages.flatMap((page) => page.data) ?? [], [pages.data]);
  const navList = useMemo(
    () =>
      items.map((item) => ({
        id: item.card_id,
        name: item.name ?? item.label ?? '',
        reprints: (item.group_card_ids?.length ?? 0) > 1,
      })),
    [items],
  );

  const firstPage = pages.data?.pages[0];
  const specs = selectSpecs(meta, sets.data?.data ?? []);

  return (
    <AsyncView queries={[pages, sets]}>
      <PageTitle>Cartas</PageTitle>
      {firstPage && <Totals totals={firstPage.totals} showAll={showAll} />}

      <div className="my-3 flex flex-wrap gap-x-4 gap-y-2">
        <ChipGroup
          size="md"
          options={MODE_OPTIONS}
          value={showAll ? '1' : ''}
          onChange={(value) => filters.set({ show_all: value, unique_reprints: '' })}
        />
        <ChipGroup
          size="md"
          options={HALL_OF_FAME_OPTIONS}
          value={filters.get('rating_min') ? '1' : ''}
          onChange={(value) => filters.set({ rating_min: value, rating: '' })}
        />
        {showAll && (
          <ChipGroup
            size="md"
            options={REPRINT_OPTIONS}
            value={filters.get('unique_reprints') ? '1' : ''}
            onChange={(value) => filters.set({ unique_reprints: value })}
          />
        )}
      </div>

      <Toolbar>
        <SearchBox value={filters.get('q')} onSubmit={(q) => filters.set({ q })} />
        {SELECT_FILTERS.map((key) => (
          <Select
            key={key}
            aria-label={specs[key].placeholder}
            placeholder={specs[key].placeholder}
            options={specs[key].options}
            value={filters.get(key)}
            onChange={(value) => filters.set({ [key]: value })}
          />
        ))}
        <Select
          aria-label="Orden"
          options={SORT_OPTIONS}
          value={filters.get('sort')}
          onChange={(sort) => filters.set({ sort })}
        />
      </Toolbar>

      {items.length === 0 ? (
        <EmptyState>No hay cartas con estos filtros.</EmptyState>
      ) : (
        <CardGrid>
          {items.map((item, index) => (
            <CollectionTile
              key={`${item.card_id}-${item.id ?? 'slot'}`}
              item={item}
              onClick={() => openFromList(navList, index)}
            />
          ))}
        </CardGrid>
      )}

      {pages.hasNextPage && (
        <div className="my-6 text-center">
          <button
            type="button"
            disabled={pages.isFetchingNextPage}
            onClick={() => void pages.fetchNextPage()}
            className="rounded-card border border-line bg-surface-2 px-6 py-3 text-sm hover:border-accent disabled:opacity-50"
          >
            Mostrando {items.length} de {firstPage?.total} - Cargar más
          </button>
        </div>
      )}
    </AsyncView>
  );
}

function Totals({ totals, showAll }: { totals: CollectionTotals; showAll: boolean }) {
  return (
    <Subtitle>
      {showAll
        ? `${totals.owned_slots ?? 0} / ${totals.slots ?? 0} cartas conseguidas · ${totals.physical_cards} físicas`
        : `${totals.unique_cards} cartas diferentes · ${totals.physical_cards} cartas físicas · ${totals.item_rows} registros`}
    </Subtitle>
  );
}

/** Text search that applies on Enter or blur, not on every keystroke. */
function SearchBox({ value, onSubmit }: { value: string; onSubmit: (q: string) => void }) {
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  if (synced !== value) {
    // The URL changed under us (back button, cleared filter): follow it.
    setSynced(value);
    setDraft(value);
  }

  return (
    <Input
      type="search"
      size="toolbar"
      placeholder="Buscar…"
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => draft !== value && onSubmit(draft)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') onSubmit(draft);
      }}
    />
  );
}
