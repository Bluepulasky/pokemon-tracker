import { useState } from 'react';

import { api } from '@/api/client';
import type { CollectionItem, Photo } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { ConfirmButton } from '@/components/ui/ConfirmButton';
import { FileButton } from '@/components/ui/FileButton';
import { Tag } from '@/components/ui/typography';
import { useMeta } from '@/context/MetaContext';
import { useApiMutation } from '@/hooks/useApiMutation';
import { cn } from '@/lib/cn';
import { eur, photoUrl } from '@/lib/format';

import { Quotes } from './Quotes';
import { VariantEditForm } from './VariantEditForm';

/** One physical copy held: its tags, photos, price and actions; or its edit form. */
export function VariantCard({ item }: { item: CollectionItem }) {
  const [editing, setEditing] = useState(false);

  return (
    <div className="flex w-59 flex-none snap-start flex-col gap-2 rounded-control border border-line bg-surface-3 p-2.5">
      {editing ? (
        <VariantEditForm item={item} onClose={() => setEditing(false)} />
      ) : (
        <VariantSummary item={item} onEdit={() => setEditing(true)} />
      )}
    </div>
  );
}

function VariantSummary({ item, onEdit }: { item: CollectionItem; onEdit: () => void }) {
  const meta = useMeta();
  const upload = useApiMutation((file: File) => api.uploadPhoto(item.id, file), {
    success: 'Foto subida',
  });
  const remove = useApiMutation(() => api.deleteItem(item.id), { success: 'Registro eliminado' });

  const labelOf = (options: { key: string; label: string }[], key: string) =>
    options.find((option) => option.key === key)?.label ?? key;
  // Which printing this copy is, e.g. FO-13.
  const printingCode = item.set_code && item.number ? `${item.set_code}-${item.number}` : '';
  const value = item.value ?? {};

  return (
    <>
      <div className="flex flex-wrap gap-1">
        <Tag>{labelOf(meta.variants, item.variant)}</Tag>
        <Tag>{item.condition}</Tag>
        <Tag>{labelOf(meta.languages, item.language)}</Tag>
        {printingCode && <Tag title={item.printing_name}>{printingCode}</Tag>}
      </div>

      <PhotoStrip photos={item.photos} />

      <div className="font-semibold tabular-nums">
        {eur(value.total)}{' '}
        <small className="font-normal text-fg-faint">
          {value.basis === 'no_data'
            ? 'sin datos para esta impresión'
            : `${eur(value.unit)} × ${item.quantity}${
                value.basis === 'printing_level' ? ' · precio de la impresión' : ''
              }`}
        </small>
      </div>

      {item.market_url && (
        <a
          href={item.market_url}
          target="_blank"
          rel="noopener noreferrer"
          className="w-fit rounded-full border border-accent-2/35 bg-accent-2/10 px-2.5 py-0.5 text-[11px] font-semibold text-accent-2 transition hover:border-accent-2 hover:bg-accent-2/20"
        >
          Cardmarket ↗
        </a>
      )}
      <Quotes cardId={item.card_id} variant={item.variant} />

      <div className="flex gap-1.5 *:flex-1">
        <FileButton size="xs" accept="image/*" disabled={upload.isPending} onFile={upload.mutate}>
          {upload.isPending ? 'Subiendo…' : 'Foto'}
        </FileButton>
        <Button size="xs" onClick={onEdit}>
          Editar
        </Button>
        <ConfirmButton
          size="xs"
          confirmLabel="¿Seguro?"
          busy={remove.isPending}
          onConfirm={() => remove.mutate()}
        >
          Borrar
        </ConfirmButton>
      </div>
    </>
  );
}

/** A copy's photos, swipeable; clicking one makes it the primary. */
function PhotoStrip({ photos }: { photos: Photo[] }) {
  const setPrimary = useApiMutation(api.setPrimaryPhoto, {
    success: 'Foto principal actualizada',
  });

  if (!photos.length) {
    return (
      <div className="flex aspect-card w-full flex-col items-center justify-center gap-1 rounded-control border border-dashed border-line text-center text-xs text-fg-faint">
        <span>Sin fotografía</span>
        <small className="text-[11px] opacity-80">Toca «Foto» para añadir una</small>
      </div>
    );
  }

  return (
    <div className="flex snap-x snap-mandatory gap-1.5 overflow-x-auto rounded-control bg-surface">
      {photos.map((photo) => (
        <img
          key={photo.id}
          src={photoUrl(photo, false)}
          alt=""
          loading="lazy"
          role="button"
          title={photo.is_primary ? 'Principal' : 'Marcar como principal'}
          onClick={() => setPrimary.mutate(photo.id)}
          className={cn(
            'aspect-card w-full flex-none snap-center rounded-control border-[3px] object-cover transition',
            photo.is_primary ? 'border-accent' : 'border-transparent hover:border-fg-faint',
          )}
        />
      ))}
    </div>
  );
}
