import type { CardImageSource, Photo } from '@/api/types';

/** Formats euros the Spanish way; whole euros from 100 up. `null` renders as a dash. */
export function eur(n: number | null | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: n >= 100 ? 0 : 2,
  }).format(n);
}

/** One-decimal percentage, without a trailing ".0". */
export function pct(n: number | null | undefined): string {
  return `${(n ?? 0).toFixed(1).replace('.0', '')}%`;
}

/** `fo-13-whatever` → `FO-13`: the set code and number of a card id. */
export function shortId(cardId: string): string {
  return cardId.split('-').slice(0, 2).join('-').toUpperCase();
}

/** Catalogue art for a card: the locally cached copy when there is one. */
export function cardArt(card: CardImageSource): string {
  if (card.image_local) return `/media/${card.image_local}`;
  return card.image_small_url ?? '';
}

/** URL of a user photo; the thumbnail unless `thumb` is false or none exists. */
export function photoUrl(photo: Photo, thumb = true): string {
  const file = thumb && photo.thumb_filename ? photo.thumb_filename : photo.filename;
  return `/media/${file}`;
}

/** Rounds to the cent, the way the backend does. */
export function cents(n: number): number {
  return Number(n.toFixed(2));
}

/** Completion as 0–100, clamped. */
export function ratio(owned: number, target: number): number {
  return target ? Math.min(100, (100 * owned) / target) : 0;
}
