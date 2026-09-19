import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

type Patch = Record<string, string | null | undefined>;

/**
 * Filter state kept in the URL query, so a filtered view can be bookmarked and
 * survives a reload. `get` falls back to `defaults`; `set` drops blank values.
 */
export function useUrlFilters<K extends string>(defaults: Record<K, string>) {
  const [params, setParams] = useSearchParams();

  const get = (key: K): string => params.get(key) ?? defaults[key];

  const set = useCallback(
    (patch: Patch) => {
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      });
    },
    [setParams],
  );

  return { get, set, params };
}
