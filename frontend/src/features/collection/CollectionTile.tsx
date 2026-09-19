import type { CollectionItem } from '@/api/types';
import { CardBadge } from '@/components/cards/CardBadge';
import { CardCaption, CardTile } from '@/components/cards/CardTile';
import { cardArt, eur, photoUrl, shortId } from '@/lib/format';

/** The image of a tile: the user's best photo when the card is owned, else catalogue art. */
function tileImage(item: CollectionItem, owned: boolean): string {
  if (!owned) return cardArt(item);
  const photo =
    item.display_photo ??
    item.photos?.find((candidate) => candidate.is_primary) ??
    item.photos?.[0];
  return photo ? photoUrl(photo) : cardArt(item);
}

interface Props {
  item: CollectionItem;
  onClick: () => void;
}

/** One card of the Cartas grid, standing for every copy (and reprint) grouped behind it. */
export function CollectionTile({ item, onClick }: Props) {
  const owned = item.owned !== false;
  const name = item.name ?? item.label ?? '—';
  const quantity = item.group_quantity ?? item.quantity;
  const value = item.value ?? {};
  const price = value.total != null ? `${value.partial ? '≥' : ''}${eur(value.total)}` : '';

  return (
    <CardTile
      name={name}
      image={tileImage(item, owned)}
      number={item.number}
      setCode={item.official_set_id}
      missing={!owned}
      framed
      onClick={onClick}
      overlay={
        <>
          {!!item.rating && (
            <CardBadge corner="top-left" tone={item.rating < 7 ? 'blue' : 'accent'}>
              ★{item.rating}
            </CardBadge>
          )}
          {owned && quantity > 1 && (
            <CardBadge corner="top-right" tone="accent">
              ×{quantity}
            </CardBadge>
          )}
          {owned && price && (
            <CardBadge
              corner="bottom-left"
              tone="dark"
              title={
                value.partial ? 'Alguna copia no tiene precio: el total es un mínimo.' : undefined
              }
            >
              {price}
            </CardBadge>
          )}
          {item.reprint_owned && (
            <CardBadge
              corner="bottom-right"
              tone="muted"
              title="No tenés esta impresión, pero sí otra versión de la carta"
            >
              otra versión
            </CardBadge>
          )}
        </>
      }
      caption={
        <CardCaption
          name={name}
          muted={!owned}
          detail={`${shortId(item.card_id)}${owned && item.condition ? ` - ${item.condition}` : ''}`}
        />
      }
    />
  );
}
