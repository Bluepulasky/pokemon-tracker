import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { useCardModal } from '@/context/CardModalContext';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { cardArt } from '@/lib/format';

const MIN_QUERY_LENGTH = 2;

/** The header search box: type a name, pick a card, its modal opens. */
export function GlobalSearch() {
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const { openCard } = useCardModal();

  const query = useDebouncedValue(text.trim(), 220);
  const enabled = query.length >= MIN_QUERY_LENGTH;
  const { data } = useQuery({
    queryKey: queryKeys.search(query),
    queryFn: () => api.search(query),
    enabled,
  });

  useEffect(() => {
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('click', closeOnOutsideClick);
    return () => document.removeEventListener('click', closeOnOutsideClick);
  }, []);

  const owned = new Set(data?.collection.map((item) => item.card_id));

  const pick = (cardId: string) => {
    setOpen(false);
    setText('');
    openCard(cardId);
  };

  return (
    <div ref={wrapper} className="relative max-md:order-3 max-md:mb-2.5 max-md:w-full md:ml-auto">
      <input
        type="search"
        value={text}
        placeholder="Buscar carta…"
        autoComplete="off"
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        className="w-full rounded-full border border-line bg-surface-2 px-3 py-2 outline-none focus:border-accent-2 max-md:text-base md:w-55 md:focus:w-70"
      />
      {open && enabled && data && (
        <div className="absolute top-10.5 right-0 max-h-[60vh] w-full overflow-y-auto rounded-card border border-line bg-surface-2 p-1.5 shadow-pop md:w-85">
          {data.cards.length === 0 && (
            <div className="p-2.5 text-xs text-fg-dim">Sin resultados</div>
          )}
          {data.cards.map((card) => (
            <button
              key={card.id}
              type="button"
              onClick={() => pick(card.id)}
              className="flex w-full items-center gap-2.5 rounded-control p-2 text-left hover:bg-surface-3"
            >
              <img src={cardArt(card)} alt="" loading="lazy" className="w-7.5 rounded-[3px]" />
              <div>
                <div>{card.name}</div>
                <div className="text-xs text-fg-dim">
                  {card.set_name} #{card.number}
                  {owned.has(card.id) && ' · en colección'}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
