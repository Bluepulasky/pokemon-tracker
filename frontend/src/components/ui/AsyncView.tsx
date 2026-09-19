import type { ReactNode } from 'react';

import { EmptyState } from './EmptyState';

interface QueryLike {
  isPending: boolean;
  error: Error | null;
}

interface Props {
  /** Every query the view needs before it can render. */
  queries: readonly QueryLike[];
  children: ReactNode;
}

/** Renders `children` once all `queries` have data; a loading or error line until then. */
export function AsyncView({ queries, children }: Props) {
  const error = queries.find((query) => query.error)?.error;
  if (error) return <EmptyState>Error: {error.message}</EmptyState>;
  if (queries.some((query) => query.isPending)) return <EmptyState>Cargando…</EmptyState>;
  return <>{children}</>;
}
