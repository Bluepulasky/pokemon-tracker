import { QueryClient } from '@tanstack/react-query';

import { queryKeys } from './queryKeys';

/* No automatic retries or focus refetches: a request the user did not ask for
   can reach tcggo, which bills per request (the episode search does). */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false, staleTime: 30_000 },
    mutations: { retry: false },
  },
});

const EPISODES_KEY = queryKeys.episodes('')[0];

/** Marks every cached read stale except the episode search, which may cost a request. */
export function invalidateAppData(client: QueryClient): Promise<void> {
  return client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== EPISODES_KEY });
}
