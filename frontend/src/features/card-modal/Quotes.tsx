import { useQuery } from '@tanstack/react-query';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';

const STORES: Record<string, string> = { cardmarket: 'Cardmarket', tcgplayer: 'TCGplayer' };
const PREFERRED_PROVIDER = 'tcggo';

function money(value: number, currency: string): string {
  return currency === 'USD' ? `$${value.toFixed(2)}` : `${value.toFixed(2)} €`;
}

/** Where a copy's price comes from: the preferred source by name, otherwise the alternatives. */
export function Quotes({ cardId, variant }: { cardId: string; variant: string }) {
  const { data } = useQuery({
    queryKey: queryKeys.quotes(cardId, variant),
    queryFn: () => api.quotes(cardId, variant),
  });

  const usable = (data?.quotes ?? []).filter((quote) => quote.trusted && quote.price != null);
  if (!usable.length) return null;

  const preferred = usable.find(
    (quote) => quote.provider === PREFERRED_PROVIDER && quote.market === 'cardmarket',
  );
  if (preferred) {
    return <div className="text-xs text-fg-dim">{STORES[preferred.market]}</div>;
  }

  return (
    <ul className="text-[13px] text-fg-dim">
      {usable.map((quote) => (
        <li key={`${quote.provider}-${quote.market}`} className="flex justify-between gap-3">
          <span>{STORES[quote.market] ?? quote.market}</span>
          <span className="tabular-nums">{money(quote.price ?? 0, quote.currency)}</span>
        </li>
      ))}
    </ul>
  );
}
