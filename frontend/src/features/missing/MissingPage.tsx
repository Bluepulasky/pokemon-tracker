import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { MissingRow } from '@/api/types';
import { AsyncView } from '@/components/ui/AsyncView';
import { Select } from '@/components/ui/controls';
import { EmptyState } from '@/components/ui/EmptyState';
import { ListRow, ListRows } from '@/components/ui/ListRow';
import { Toolbar } from '@/components/ui/Toolbar';
import { PageTitle, Subtitle, Tag } from '@/components/ui/typography';
import { useCardModal } from '@/context/CardModalContext';
import { shortId } from '@/lib/format';

const SORT_OPTIONS = [
  { key: 'number', label: 'Por número' },
  { key: 'name', label: 'Por nombre' },
  { key: 'rarity', label: 'Por rareza' },
];

export function MissingPage() {
  const params = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const { openFromList } = useCardModal();

  const sets = useQuery({ queryKey: queryKeys.sets, queryFn: api.sets });
  const setList = sets.data?.data ?? [];
  const setId = params.setId ?? search.get('set') ?? setList[0]?.id ?? '';
  const sort = search.get('sort') ?? 'number';

  const set = useQuery({
    queryKey: queryKeys.set(setId),
    queryFn: () => api.set(setId),
    enabled: !!setId,
  });
  const missing = useQuery({
    queryKey: queryKeys.missing(setId, sort),
    queryFn: () => api.missing(setId, sort),
    enabled: !!setId,
  });

  if (sets.data && !setId) return <EmptyState>No hay sets.</EmptyState>;

  const rows = missing.data?.data ?? [];
  const navList = rows.map((row) => ({ id: row.card_id, name: row.label ?? '' }));
  const show = (nextSet: string, nextSort: string) =>
    void navigate(`/missing/${nextSet}?sort=${nextSort}`);

  return (
    <AsyncView queries={[sets, set, missing]}>
      <PageTitle>Cartas faltantes</PageTitle>
      <Subtitle>
        {set.data?.name} · {rows.filter((row) => row.missing_entirely).length} de{' '}
        {set.data?.progress?.target ?? 0} únicas · faltan{' '}
        {rows.reduce((sum, row) => sum + Math.max(0, row.still_needed), 0)} copias
      </Subtitle>

      <Toolbar>
        <Select
          aria-label="Set"
          value={setId}
          onChange={(value) => show(value, sort)}
          options={setList.map((item) => ({
            key: item.id,
            label: `${item.name} (${item.target - item.owned})`,
          }))}
        />
        <Select
          aria-label="Orden"
          value={sort}
          onChange={(value) => show(setId, value)}
          options={SORT_OPTIONS}
        />
      </Toolbar>

      {rows.length === 0 ? (
        <EmptyState>🎉 Set completo.</EmptyState>
      ) : (
        <ListRows>
          {rows.map((row, index) => (
            <ListRow
              key={row.card_id}
              lead={shortId(row.card_id)}
              trail={row.rarity ?? ''}
              onClick={() => openFromList(navList, index)}
            >
              <span>{row.label}</span>
              <CopiesTag row={row} />
            </ListRow>
          ))}
        </ListRows>
      )}
    </AsyncView>
  );
}

/** How far a card is from its target: nothing to say for a plain single missing copy. */
function CopiesTag({ row }: { row: MissingRow }) {
  if (!row.missing_entirely) {
    return (
      <Tag>
        tenés {row.held} de {row.target}
      </Tag>
    );
  }
  return row.target > 1 ? <Tag>faltan {row.still_needed} copias</Tag> : null;
}
