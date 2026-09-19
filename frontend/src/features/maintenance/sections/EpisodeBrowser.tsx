import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Episode } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/controls';
import { EmptyState } from '@/components/ui/EmptyState';
import { LogoImage } from '@/components/ui/LogoImage';
import { ErrorText } from '@/components/ui/ResultBox';
import { Note } from '@/components/ui/typography';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { cn } from '@/lib/cn';

/** Search the tcggo set list and import (or re-import) a set. */
export function EpisodeBrowser() {
  const client = useQueryClient();
  const [text, setText] = useState('');
  const query = useDebouncedValue(text.trim(), 350);

  // Never refetched on its own: a search with no local match reaches tcggo,
  // and that request is billed.
  const episodes = useQuery({
    queryKey: queryKeys.episodes(query),
    queryFn: () => api.episodes(query),
    staleTime: Infinity,
  });

  const importSet = useApiMutation(api.importEpisode, {
    success: (result) => `${result.name}: ${result.cards} cartas, ${result.requests} consultas`,
    // The listed sets are known locally, so re-listing them costs nothing.
    onDone: () => void client.invalidateQueries({ queryKey: queryKeys.episodes(query) }),
  });

  const list = [...(episodes.data?.episodes ?? [])].sort((a, b) =>
    (a.released_at ?? '').localeCompare(b.released_at ?? ''),
  );

  return (
    <>
      <div className="max-w-105">
        <Input
          type="search"
          placeholder="Neo Genesis, Fossil, BS…"
          autoComplete="off"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <Note>
          {query && episodes.data
            ? `${list.length} resultado(s) para «${query}».`
            : 'Los que ya conocés salen al instante. Buscar uno nuevo cuesta una consulta.'}
        </Note>
      </div>

      {episodes.isPending && <Note>Buscando…</Note>}
      {episodes.error && <ErrorText>{episodes.error.message}</ErrorText>}
      {episodes.data && !list.length && <EmptyState>Ningún set con ese nombre.</EmptyState>}

      <div className="mt-2.5 grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-2.5">
        {list.map((episode) => (
          <EpisodeCard
            key={episode.id}
            episode={episode}
            importing={importSet.isPending && importSet.variables === episode.id}
            disabled={importSet.isPending}
            onImport={() => importSet.mutate(episode.id)}
          />
        ))}
      </div>
    </>
  );
}

interface CardProps {
  episode: Episode;
  importing: boolean;
  disabled: boolean;
  onImport: () => void;
}

function EpisodeCard({ episode, importing, disabled, onImport }: CardProps) {
  // Listed but not offered: tcggo holds no products for it, so an import would
  // spend a request and fetch nothing.
  const empty = !!episode.empty && !episode.imported;

  return (
    <div
      className={cn(
        'rounded-lg border bg-gray-500/10 p-2.5 text-center',
        episode.imported ? 'border-good opacity-75' : 'border-transparent',
        empty && 'opacity-55',
      )}
    >
      <LogoImage src={episode.logo} className="h-11.5 w-full" />
      <div className="mt-1.5 text-[13px] font-semibold">{episode.name}</div>
      <div className="mb-1.5 text-xs text-fg-dim">
        {episode.code} · {episode.released_at?.slice(0, 4)}
        {episode.cards_total > 0 && ` · ${episode.cards_total} cartas`}
      </div>

      {episode.imported && (
        <div className="mb-1.5 text-xs text-good">{episode.products} productos importados</div>
      )}
      {empty ? (
        <div className="text-[11px] leading-tight text-fg-dim">
          tcggo no tiene cartas para este set. Si existen, están dentro de otro.
        </div>
      ) : (
        <Button
          size="xs"
          variant={episode.imported ? 'ghost' : 'default'}
          className="w-full"
          disabled={disabled}
          title={
            episode.imported
              ? 'Vuelve a traer el set — corrige datos y precios sin re-elegir cartas'
              : undefined
          }
          onClick={onImport}
        >
          {episode.imported
            ? importing
              ? 'Reimportando…'
              : 'Reimportar'
            : importing
              ? 'Importando…'
              : 'Añadir'}
        </Button>
      )}
    </div>
  );
}
