import { useQuery } from '@tanstack/react-query';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { LogoImage } from '@/components/ui/LogoImage';
import { useApiMutation } from '@/hooks/useApiMutation';

/** Sets hidden from the collection, each with a button to bring it back. */
export function HiddenSets() {
  const { data } = useQuery({ queryKey: queryKeys.hiddenSets, queryFn: api.hiddenSets });
  const show = useApiMutation((setId: string) => api.setHidden(setId, false), {
    success: 'Set visible de nuevo en la colección.',
  });

  if (!data) return null;
  if (!data.data.length) return <EmptyState>Ningún set oculto.</EmptyState>;

  return (
    <div className="flex max-w-120 flex-col gap-2">
      {data.data.map((set) => (
        <div
          key={set.id}
          className="flex items-center gap-3 rounded-control border border-line bg-surface-2 px-3 py-2"
        >
          <LogoImage src={set.logo_url} className="h-6.5 w-11.5" />
          <span className="flex-1 font-semibold">{set.name}</span>
          <Button size="xs" disabled={show.isPending} onClick={() => show.mutate(set.id)}>
            Mostrar
          </Button>
        </div>
      ))}
    </div>
  );
}
