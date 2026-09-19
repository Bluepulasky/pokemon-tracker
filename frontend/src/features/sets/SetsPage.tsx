import { useQuery } from '@tanstack/react-query';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { SetProgress } from '@/api/types';
import { SetCard, SetGrid } from '@/components/sets/SetCard';
import { AsyncView } from '@/components/ui/AsyncView';
import { PageTitle, SectionTitle, Subtitle } from '@/components/ui/typography';
import { useApiMutation } from '@/hooks/useApiMutation';

const NO_ERA = 'Otros';

/** Groups sets by era, keeping the API's release-date order within and across groups. */
function groupByEra(sets: SetProgress[]): [string, SetProgress[]][] {
  const groups = new Map<string, SetProgress[]>();
  for (const set of sets) {
    const era = set.series ?? NO_ERA;
    groups.set(era || NO_ERA, [...(groups.get(era || NO_ERA) ?? []), set]);
  }
  return [...groups];
}

export function SetsPage() {
  const sets = useQuery({ queryKey: queryKeys.sets, queryFn: api.sets });
  const hide = useApiMutation((setId: string) => api.setHidden(setId, true), {
    success: 'Set oculto. Se muestra de nuevo desde Mantenimiento.',
  });

  const list = sets.data?.data ?? [];
  const owned = list.reduce((sum, set) => sum + set.owned, 0);
  const target = list.reduce((sum, set) => sum + set.target, 0);

  return (
    <AsyncView queries={[sets]}>
      <PageTitle>Sets</PageTitle>
      <Subtitle>
        {list.length} sets personalizados · {owned} / {target} cartas
      </Subtitle>
      {groupByEra(list).map(([era, eraSets]) => (
        <section key={era}>
          <SectionTitle className="mt-3">{era}</SectionTitle>
          <SetGrid>
            {eraSets.map((set) => (
              <SetCard key={set.id} set={set} onHide={hide.mutate} />
            ))}
          </SetGrid>
        </section>
      ))}
    </AsyncView>
  );
}
