import { createContext, use, useCallback, useMemo, useState, type ReactNode } from 'react';

/** One entry of the list the modal's prev/next buttons walk through. */
export interface CardNavEntry {
  id: string;
  name: string;
  /** The tile stands for several reprints, so the modal lists all of their copies. */
  reprints?: boolean;
}

export interface OpenCardState {
  cardId: string;
  reprints: boolean;
  navList: CardNavEntry[];
  navIndex: number;
}

interface CardModalApi {
  current: OpenCardState | null;
  /** Opens a single card, with no prev/next. */
  openCard: (cardId: string) => void;
  /** Opens `list[index]`, with prev/next walking the rest of `list`. */
  openFromList: (list: CardNavEntry[], index: number) => void;
  close: () => void;
}

const CardModalContext = createContext<CardModalApi | null>(null);

export function CardModalProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<OpenCardState | null>(null);

  const openCard = useCallback((cardId: string) => {
    setCurrent({ cardId, reprints: false, navList: [], navIndex: -1 });
  }, []);

  const openFromList = useCallback((list: CardNavEntry[], index: number) => {
    const entry = list[index];
    if (!entry) return;
    setCurrent({
      cardId: entry.id,
      reprints: !!entry.reprints,
      navList: list,
      navIndex: index,
    });
  }, []);

  const close = useCallback(() => setCurrent(null), []);

  const value = useMemo(
    () => ({ current, openCard, openFromList, close }),
    [current, openCard, openFromList, close],
  );

  return <CardModalContext value={value}>{children}</CardModalContext>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useCardModal(): CardModalApi {
  const value = use(CardModalContext);
  if (!value) throw new Error('useCardModal must be used inside <CardModalProvider>');
  return value;
}
