import { useQuery } from '@tanstack/react-query';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { CardVersion } from '@/api/types';
import { LogoImage } from '@/components/ui/LogoImage';
import { Note } from '@/components/ui/typography';
import { cn } from '@/lib/cn';

interface Props {
  cardId: string;
  picked: CardVersion | null;
  onPick: (version: CardVersion) => void;
}

/** Every Cardmarket printing of a card: this set's first, then reprints in other sets. */
export function VersionPicker({ cardId, picked, onPick }: Props) {
  const { data, error, isPending } = useQuery({
    queryKey: queryKeys.versions(cardId),
    queryFn: () => api.versions(cardId),
  });

  if (isPending) return <Note>Buscando versiones…</Note>;
  if (error) {
    return <Note>No se pudieron cargar las versiones ({error.message}). Volvé a intentar.</Note>;
  }
  if (!data.versions.length) {
    return (
      <Note>
        Sin versiones conocidas para esta carta. Importá su set desde Mantenimiento para poder
        registrarla.
      </Note>
    );
  }

  const ordered = [
    ...data.versions.filter((version) => version.is_current),
    ...data.versions.filter((version) => !version.is_current),
  ];

  return (
    <>
      <div className="mt-1.5 grid max-h-125 grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-2 overflow-y-auto p-0.5">
        {ordered.map((version) => (
          <VersionTile
            key={version.market_product_id}
            version={version}
            picked={picked?.market_product_id === version.market_product_id}
            onPick={() => onPick(version)}
          />
        ))}
      </div>
      {picked && <PickedSummary version={picked} />}
    </>
  );
}

interface TileProps {
  version: CardVersion;
  picked: boolean;
  onPick: () => void;
}

function VersionTile({ version, picked, onPick }: TileProps) {
  const reprint = !version.is_current;

  return (
    <button
      type="button"
      aria-pressed={picked}
      onClick={onPick}
      className={cn(
        'flex flex-col gap-0.5 rounded-lg border-2 p-1.5 text-left',
        picked
          ? 'border-accent bg-accent/10'
          : 'border-transparent bg-gray-500/10 hover:bg-gray-500/15',
        reprint && 'opacity-80',
      )}
    >
      <LogoImage src={version.image} className="aspect-5/7 w-full rounded-sm" />
      {version.set && (
        <span
          className={cn(
            'truncate text-[11px] font-semibold',
            reprint ? 'text-fg-dim' : 'text-accent',
          )}
        >
          {version.set}
        </span>
      )}
      <span className="text-xs font-semibold">{version.code}</span>
      {version.version && (
        <span className="text-[11px] leading-tight text-fg-dim">{version.version}</span>
      )}
      <span className="text-[13px] tabular-nums">
        {version.price != null ? `${version.price.toFixed(2)} €` : '—'}
      </span>
    </button>
  );
}

function PickedSummary({ version }: { version: CardVersion }) {
  const bits = [version.code, version.set, version.version, version.rarity].filter(Boolean);

  return (
    <div className="mt-2 text-[13px] text-fg-dim">
      Se guardará como <strong>{bits.join(' · ')}</strong> — producto Cardmarket{' '}
      <code>{version.market_product_id}</code>
      {!version.is_current && (
        <Note>
          Reimpresión — se guarda en <strong>{version.set}</strong>, no en el set que abriste.
        </Note>
      )}
    </div>
  );
}
