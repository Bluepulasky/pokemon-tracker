import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { CollectionItem } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Field, Input, Select } from '@/components/ui/controls';
import { useMeta } from '@/context/MetaContext';
import { useApiMutation } from '@/hooks/useApiMutation';
import { eur } from '@/lib/format';

import { basePrice, previewPrice } from './pricing';

const YES_NO = [
  { key: '0', label: 'No' },
  { key: '1', label: 'Sí (×2)' },
];

interface Props {
  item: CollectionItem;
  onClose: () => void;
}

/** Edits one copy — edition, grade, language, quantity, manual price — with a live price. */
export function VariantEditForm({ item, onClose }: Props) {
  const meta = useMeta();
  const modifiers = useQuery({ queryKey: queryKeys.modifiers, queryFn: api.modifiers });

  // The price as typed, not as it works out after grade and language.
  const savedManual = item.value?.manual && item.value.base != null ? String(item.value.base) : '';

  const [firstEdition, setFirstEdition] = useState(!!item.first_edition);
  const [condition, setCondition] = useState(item.condition);
  const [language, setLanguage] = useState(item.language);
  const [quantity, setQuantity] = useState(item.quantity);
  const [manual, setManual] = useState(savedManual);

  const typed = manual.trim();
  const manualChanged = typed !== savedManual;

  const save = useApiMutation(
    async () => {
      await api.updateItem(item.id, {
        first_edition: firstEdition,
        condition,
        language,
        quantity: quantity || 1,
      });
      // Sent only when it changed, and against the copy's own card and variant:
      // in a grouped modal that is not always the card the modal was opened on.
      if (manualChanged) {
        await api.setManualPrice(item.card_id, item.variant, typed === '' ? null : Number(typed));
      }
    },
    {
      success: manualChanged && typed === '' ? 'Precio manual quitado' : 'Actualizado',
      onDone: onClose,
    },
  );

  const base = typed !== '' ? Number(typed) : basePrice(item);
  const preview =
    base != null && Number.isFinite(base)
      ? previewPrice({
          base,
          firstEdition,
          quantity: quantity || 1,
          conditionMultiplier: modifiers.data?.condition?.[condition] ?? 1,
          languageMultiplier:
            meta.languages.find((option) => option.key === language)?.multiplier ?? 1,
        })
      : null;

  return (
    <div className="grid gap-2">
      <Field label="¿Primera edición?">
        <Select
          size="field"
          options={YES_NO}
          value={firstEdition ? '1' : '0'}
          onChange={(value) => setFirstEdition(value === '1')}
        />
      </Field>
      <Field label="Condición">
        <Select
          size="field"
          value={condition}
          onChange={setCondition}
          options={meta.conditions.map((option) => ({
            key: option.key,
            label: `${option.key} — ${option.label}`,
          }))}
        />
      </Field>
      <Field label="Idioma">
        <Select size="field" options={meta.languages} value={language} onChange={setLanguage} />
      </Field>
      <Field label="Cantidad">
        <Input
          type="number"
          min={1}
          inputMode="numeric"
          value={quantity}
          onChange={(event) => setQuantity(Number(event.target.value))}
        />
      </Field>
      <Field label="Precio manual">
        <Input
          type="number"
          min={0}
          step={0.01}
          inputMode="decimal"
          placeholder="ingrese precio manual"
          value={manual}
          onChange={(event) => setManual(event.target.value)}
        />
      </Field>

      {preview && (
        <div className="font-semibold tabular-nums">
          {eur(preview.total)}{' '}
          <small className="font-normal text-fg-faint">
            ({eur(preview.unit)} × {quantity || 1}
            {typed !== '' && ' - manual'})
          </small>
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>
          Guardar
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
