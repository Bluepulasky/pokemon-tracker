import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { CardDetail, CollectionItem } from '@/api/types';
import { Accordion } from '@/components/ui/Accordion';
import { EmptyState } from '@/components/ui/EmptyState';
import { RangeField } from '@/components/ui/RangeField';
import { useCardModal, type CardNavEntry, type OpenCardState } from '@/context/CardModalContext';
import { useToast } from '@/context/ToastContext';
import { useApiMutation } from '@/hooks/useApiMutation';
import { cn } from '@/lib/cn';
import { cardArt, shortId } from '@/lib/format';

import { AddCopyForm } from './AddCopyForm';
import { VariantCard } from './VariantCard';

const MAX_RANK = 8;
const MAX_TARGET = 8;

/** The card modal: catalogue info, the copies held, and the form to register another. */
export function CardModal() {
  const { current, close } = useCardModal();

  useEffect(() => {
    if (!current) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [current, close]);

  if (!current) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      className="fixed inset-0 z-100 flex items-end justify-center bg-black/65 backdrop-blur-sm md:items-center md:p-6"
    >
      <div className="h-[min(96vh,900px)] w-full overflow-hidden rounded-t-2xl border border-line bg-surface-2 shadow-pop md:h-[90vh] md:w-[min(90%,1400px)] md:rounded-2xl">
        {/* Keyed so sliders and forms start fresh on each card. */}
        <CardModalBody key={current.cardId} state={current} />
      </div>
    </div>
  );
}

function CardModalBody({ state }: { state: OpenCardState }) {
  const { close, openCard } = useCardModal();
  const toast = useToast();
  const { cardId, reprints } = state;

  const card = useQuery({ queryKey: queryKeys.card(cardId), queryFn: () => api.card(cardId) });
  const items = useQuery({
    queryKey: queryKeys.cardItems(cardId, reprints),
    queryFn: () => api.itemsByCard(cardId, reprints),
  });

  const error = card.error ?? items.error;
  useEffect(() => {
    if (!error) return;
    toast(error.message, true);
    close();
  }, [error, toast, close]);

  if (!card.data || !items.data) return <EmptyState className="p-10">Cargando…</EmptyState>;

  const copies = items.data.data;
  const hasCopies = copies.length > 0;

  return (
    <div className="flex h-full flex-col overflow-y-auto md:grid md:grid-cols-2 md:overflow-hidden">
      <CardArtPane card={card.data} state={state} />

      <div className="flex min-h-0 min-w-0 flex-col md:overflow-y-auto">
        <CardHeader card={card.data} copies={copies} onClose={close} />
        <Accordion
          defaultOpen={hasCopies ? 'copies' : 'add'}
          sections={[
            {
              id: 'copies',
              title: 'Variantes en colección',
              content: (
                <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2">
                  {copies.map((item) => (
                    <VariantCard key={item.id} item={item} />
                  ))}
                </div>
              ),
            },
            {
              id: 'add',
              title: hasCopies ? 'Añadir otra' : 'Registrar carta',
              content: (
                <AddCopyForm
                  card={card.data}
                  onCancel={close}
                  onAdded={(storedUnder) => {
                    if (storedUnder !== cardId) openCard(storedUnder);
                  }}
                />
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}

function CardArtPane({ card, state }: { card: CardDetail; state: OpenCardState }) {
  const { openFromList } = useCardModal();
  const { navList, navIndex } = state;

  return (
    <div className="flex h-[min(46vh,440px)] min-h-0 flex-none flex-col items-center justify-center border-b border-line bg-surface p-4 pb-2 md:h-auto md:border-r md:border-b-0 md:p-7">
      <img
        src={cardArt(card)}
        alt={card.name}
        className="min-h-0 w-auto max-w-full flex-1 rounded-card object-contain md:max-w-[90%]"
      />
      <div className="mt-2 flex w-full justify-between max-sm:hidden">
        <NavButton
          entry={navList[navIndex - 1]}
          side="left"
          onClick={() => openFromList(navList, navIndex - 1)}
        />
        <NavButton
          entry={navList[navIndex + 1]}
          side="right"
          onClick={() => openFromList(navList, navIndex + 1)}
        />
      </div>
    </div>
  );
}

interface NavButtonProps {
  entry: CardNavEntry | undefined;
  side: 'left' | 'right';
  onClick: () => void;
}

function NavButton({ entry, side, onClick }: NavButtonProps) {
  if (!entry) return <span />;
  const label = `${shortId(entry.id)} ${entry.name}`;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'max-w-[48%] truncate px-8 text-lg text-fg-dim hover:text-fg',
        side === 'right' && 'text-right',
      )}
    >
      {side === 'left' ? `‹‹ ${label}` : `${label} ››`}
    </button>
  );
}

interface HeaderProps {
  card: CardDetail;
  copies: CollectionItem[];
  onClose: () => void;
}

function CardHeader({ card, copies, onClose }: HeaderProps) {
  const rate = useApiMutation((rating: number) => api.rateCard(card.id, rating));
  const setTarget = useApiMutation((target: number) => api.setTarget(card.id, target));

  const owned = copies.reduce((sum, item) => sum + item.quantity, 0);
  const target = card.target || 1;

  return (
    <div className="relative border-b border-line px-4.5 py-5.5 md:p-7">
      <button
        type="button"
        aria-label="Cerrar"
        onClick={onClose}
        className="absolute top-3.5 right-3.5 rounded-md px-2 py-1 text-[26px] leading-none text-fg-dim hover:bg-surface-3 hover:text-fg md:top-5 md:right-5"
      >
        ×
      </button>

      <div className="pr-10">
        <h3 className="mb-1.5 text-[21px] leading-tight font-bold tracking-tight md:text-2xl">
          {card.market_url ? (
            <a
              href={card.market_url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
            >
              {card.name}
            </a>
          ) : (
            card.name
          )}
        </h3>
        <div className="text-xs text-fg-dim md:text-[13px]">
          {card.set_name} #{card.number}
          {card.rarity && ` · ${card.rarity}`}
        </div>
        <div className="text-xs text-fg-dim md:text-[13px]">{card.artist}</div>
      </div>

      <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:gap-4">
        <RangeField
          label="Hall of Fame"
          min={0}
          max={MAX_RANK}
          value={card.rating || 0}
          display={(value) => <SliderValue>{value}</SliderValue>}
          onCommit={rate.mutate}
        />
        <RangeField
          label="Objetivo de copias"
          min={1}
          max={Math.max(MAX_TARGET, target)}
          value={target}
          display={(value) => (
            <SliderValue good={owned >= value}>
              {owned} / {value}
            </SliderValue>
          )}
          onCommit={setTarget.mutate}
        />
      </div>
    </div>
  );
}

function SliderValue({ good, children }: { good?: boolean; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        'text-[13px] font-semibold tracking-normal normal-case',
        good ? 'text-good' : 'text-fg',
      )}
    >
      {children}
    </span>
  );
}
