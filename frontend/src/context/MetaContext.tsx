import { useQuery } from '@tanstack/react-query';
import { createContext, use, type ReactNode } from 'react';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Meta } from '@/api/types';
import { EmptyState } from '@/components/ui/EmptyState';

const MetaContext = createContext<Meta | null>(null);

/** Loads the API vocabularies once and blocks the app until they are in. */
export function MetaProvider({ children }: { children: ReactNode }) {
  const { data, error } = useQuery({
    queryKey: queryKeys.meta,
    queryFn: api.meta,
    staleTime: Infinity,
  });

  if (error) {
    return (
      <EmptyState className="p-10">
        No se pudo contactar con la API.
        <br />
        <small>{error.message}</small>
      </EmptyState>
    );
  }
  if (!data) return <EmptyState className="p-10">Cargando…</EmptyState>;
  return <MetaContext value={data}>{children}</MetaContext>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useMeta(): Meta {
  const meta = use(MetaContext);
  if (!meta) throw new Error('useMeta must be used inside <MetaProvider>');
  return meta;
}
