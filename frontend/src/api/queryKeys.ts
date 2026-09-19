import type { CollectionFilters } from './types';

/** Cache keys, in one place so a query and its invalidation cannot drift apart. */
export const queryKeys = {
  meta: ['meta'] as const,
  dashboard: ['dashboard'] as const,
  history: ['history'] as const,
  sets: ['sets'] as const,
  set: (id: string) => ['set', id] as const,
  missing: (id: string, sort: string) => ['missing', id, sort] as const,
  collection: (filters: CollectionFilters) => ['collection', filters] as const,
  search: (q: string) => ['search', q] as const,
  card: (id: string) => ['card', id] as const,
  cardItems: (id: string, reprints: boolean) => ['card-items', id, reprints] as const,
  versions: (cardId: string) => ['versions', cardId] as const,
  quotes: (cardId: string, variant: string) => ['quotes', cardId, variant] as const,
  modifiers: ['modifiers'] as const,
  jobStatus: ['job-status'] as const,
  health: ['health'] as const,
  hiddenSets: ['hidden-sets'] as const,
  episodes: (q: string) => ['episodes', q] as const,
};
