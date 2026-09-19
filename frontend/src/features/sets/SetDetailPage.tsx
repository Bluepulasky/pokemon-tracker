import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { Link, useParams } from 'react-router';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { SetCardEntry, SetDetail, SetProgress } from '@/api/types';
import { CardBadge } from '@/components/cards/CardBadge';
import { CardGrid, CardTile } from '@/components/cards/CardTile';
import { AsyncView } from '@/components/ui/AsyncView';
import { ChipGroup, type ChipOption } from '@/components/ui/ChipGroup';
import { Select } from '@/components/ui/controls';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Toolbar } from '@/components/ui/Toolbar';
import { PageTitle, Subtitle } from '@/components/ui/typography';
import { useCardModal } from '@/context/CardModalContext';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useUrlFilters } from '@/hooks/useUrlFilters';
import { cn } from '@/lib/cn';
import { cardArt } from '@/lib/format';

type RarityFilter = 'all' | 'holo' | 'no-holo';
type OwnedFilter = 'all' | 'owned' | 'missing';
type CollectingFilter = 'all' | 'collecting' | 'not';
type SortKey = 'number' | 'name' | 'rarity';

const RARITY_OPTIONS: ChipOption<RarityFilter>[] = [
  { value: 'all', label: 'Todas' },
  { value: 'holo', label: 'Holo' },
  { value: 'no-holo', label: 'No holo' },
];
const OWNED_OPTIONS: ChipOption<OwnedFilter>[] = [
  { value: 'all', label: 'Todas' },
  { value: 'owned', label: 'Poseídas' },
  { value: 'missing', label: 'Faltantes' },
];
const COLLECTING_OPTIONS: ChipOption<CollectingFilter>[] = [
  { value: 'all', label: 'Todas' },
  { value: 'collecting', label: 'Coleccionando' },
  { value: 'not', label: 'No coleccionando' },
];
const SORT_OPTIONS = [
  { key: 'number', label: 'Número' },
  { key: 'name', label: 'Nombre' },
  { key: 'rarity', label: 'Rareza' },
];

const FILTER_DEFAULTS = { sort: 'number', rar: 'all', own: 'all', col: 'collecting' };

const byNumber = (a: SetCardEntry, b: SetCardEntry) => (a.number_sort ?? 0) - (b.number_sort ?? 0);

const SORTERS: Record<SortKey, (a: SetCardEntry, b: SetCardEntry) => number> = {
  number: byNumber,
  name: (a, b) => a.name.localeCompare(b.name),
  rarity: (a, b) => (a.rarity ?? '').localeCompare(b.rarity ?? '') || byNumber(a, b),
};

const isHolo = (card: SetCardEntry) => /holo/i.test(card.rarity ?? '');
const isOwned = (card: SetCardEntry) => card.owned_qty > 0;

export function SetDetailPage() {
  const { setId = '' } = useParams();
  const set = useQuery({ queryKey: queryKeys.set(setId), queryFn: () => api.set(setId) });
  const sets = useQuery({ queryKey: queryKeys.sets, queryFn: api.sets });

  return (
    <AsyncView queries={[set, sets]}>
      {set.data && sets.data && <SetDetailContent set={set.data} allSets={sets.data.data} />}
    </AsyncView>
  );
}

function SetDetailContent({ set, allSets }: { set: SetDetail; allSets: SetProgress[] }) {
  const filters = useUrlFilters(FILTER_DEFAULTS);
  const { openFromList } = useCardModal();

  const rarity = filters.get('rar') as RarityFilter;
  const owned = filters.get('own') as OwnedFilter;
  const collecting = filters.get('col') as CollectingFilter;
  const sort = filters.get('sort') as SortKey;

  const shown = useMemo(
    () =>
      set.cards
        .filter((card) => rarity === 'all' || isHolo(card) === (rarity === 'holo'))
        .filter((card) => owned === 'all' || isOwned(card) === (owned === 'owned'))
        .filter(
          (card) => collecting === 'all' || !!card.collecting === (collecting === 'collecting'),
        )
        .sort(SORTERS[sort] ?? byNumber),
    [set.cards, rarity, owned, collecting, sort],
  );

  const navList = useMemo(() => shown.map((card) => ({ id: card.id, name: card.name })), [shown]);

  const toggleLoose = useApiMutation((enabled: boolean) => api.setLoose(set.id, enabled));
  const toggleCollecting = useApiMutation((card: SetCardEntry) =>
    api.setCardInSet(set.id, card.id, card.collecting ? 'drop' : 'keep'),
  );

  const index = allSets.findIndex((other) => other.id === set.id);
  const collectingCount = set.cards.filter((card) => card.collecting).length;
  const ownedCount = set.progress?.owned ?? 0;

  return (
    <>
      <div className="mb-3 flex min-w-0 items-center gap-2">
        <SetNavLink set={allSets[index - 1]} side="left" />
        <div className="min-w-0 flex-1 text-center">
          <PageTitle className="mb-0">{set.name}</PageTitle>
          <Subtitle>
            {ownedCount} / {collectingCount}
          </Subtitle>
        </div>
        <SetNavLink set={allSets[index + 1]} side="right" />
      </div>
      <ProgressBar value={ownedCount} max={collectingCount} />

      <label className="mt-3.5 inline-flex items-center gap-2 text-[13px] text-fg-dim">
        <input
          type="checkbox"
          className="accent-accent"
          checked={set.loose_completion}
          disabled={toggleLoose.isPending}
          onChange={(event) => toggleLoose.mutate(event.target.checked)}
        />
        Cualquier versión cuenta para el progreso
      </label>

      <Toolbar>
        <ChipGroup
          options={RARITY_OPTIONS}
          value={rarity}
          onChange={(rar) => filters.set({ rar })}
        />
        <ChipGroup options={OWNED_OPTIONS} value={owned} onChange={(own) => filters.set({ own })} />
        <ChipGroup
          options={COLLECTING_OPTIONS}
          value={collecting}
          onChange={(col) => filters.set({ col })}
        />
        <Select
          aria-label="Orden"
          options={SORT_OPTIONS}
          value={sort}
          onChange={(value) => filters.set({ sort: value })}
        />
      </Toolbar>

      <CardGrid>
        {shown.map((card, cardIndex) => (
          <CardTile
            key={card.id}
            name={card.name}
            image={cardArt(card)}
            number={card.number}
            setCode={card.official_set_id}
            missing={!isOwned(card)}
            dimmed={!card.collecting}
            onClick={() => openFromList(navList, cardIndex)}
            overlay={
              <>
                {isOwned(card) && (
                  <CardBadge corner="top-right" tone="good">
                    ✓{card.owned_qty > 1 && ` ×${card.owned_qty}`}
                  </CardBadge>
                )}
                <CollectToggle
                  collecting={!!card.collecting}
                  disabled={toggleCollecting.isPending}
                  onToggle={() => toggleCollecting.mutate(card)}
                />
              </>
            }
          />
        ))}
      </CardGrid>
    </>
  );
}

function SetNavLink({ set, side }: { set: SetProgress | undefined; side: 'left' | 'right' }) {
  const arrow = <span className="shrink-0 max-sm:text-lg">{side === 'left' ? '‹‹' : '››'}</span>;

  return (
    <div className="min-w-0 flex-[0_0_80px] sm:flex-[0_0_250px]">
      {set && (
        <Link
          to={`/set/${set.id}`}
          className={cn(
            'flex w-fit max-w-full items-center gap-1 py-1 text-fg-dim hover:text-fg',
            side === 'right' && 'ml-auto',
          )}
        >
          {side === 'left' && arrow}
          <span className="truncate max-sm:hidden">{set.name}</span>
          {side === 'right' && arrow}
        </Link>
      )}
    </div>
  );
}

interface CollectToggleProps {
  collecting: boolean;
  disabled: boolean;
  onToggle: () => void;
}

/** The ★ on a card: whether it counts towards this set's completion. */
function CollectToggle({ collecting, disabled, onToggle }: CollectToggleProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={
        collecting
          ? 'Coleccionando — clic para sacar de la lista'
          : 'No en la lista — clic para coleccionar'
      }
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      className={cn(
        'absolute top-1 left-1 z-10 flex size-6.5 items-center justify-center rounded-full bg-black/55 text-[15px] leading-none hover:bg-black/80',
        collecting ? 'text-accent' : 'text-[#9aa0a6]',
      )}
    >
      {collecting ? '★' : '☆'}
    </button>
  );
}
