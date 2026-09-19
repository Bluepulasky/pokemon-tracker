import { useState, type FormEvent } from 'react';

import { api } from '@/api/client';
import type { CardDetail, CardVersion } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { ChipGroup } from '@/components/ui/ChipGroup';
import { Field, FieldLabel, Input, Select } from '@/components/ui/controls';
import { useMeta } from '@/context/MetaContext';
import { useToast } from '@/context/ToastContext';
import { useApiMutation } from '@/hooks/useApiMutation';

import { VersionPicker } from './VersionPicker';

const DEFAULT_LANGUAGE = 'en';

interface Props {
  card: CardDetail;
  onCancel: () => void;
  /** Called with the card the copy was stored under — a reprint's own card, not always `card`. */
  onAdded: (cardId: string) => void;
}

/** Registers a physical copy: which printing, language, grade and how many. */
export function AddCopyForm({ card, onCancel, onAdded }: Props) {
  const meta = useMeta();
  const toast = useToast();

  const [version, setVersion] = useState<CardVersion | null>(null);
  const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
  const [quantity, setQuantity] = useState(1);
  const [condition, setCondition] = useState(meta.conditions[0]?.key ?? '');

  const add = useApiMutation(api.addItem, {
    success: `${card.name} añadida`,
    onDone: (_result, item) => onAdded(item.card_id),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!version) {
      toast('Elegí una versión de Cardmarket', true);
      return;
    }
    add.mutate({
      card_id: version.card_id ?? card.id,
      market_product_id: version.market_product_id,
      language,
      condition,
      quantity: quantity || 1,
    });
  };

  return (
    <form onSubmit={submit} className="grid gap-3">
      <div>
        <FieldLabel>Versión en Cardmarket</FieldLabel>
        <VersionPicker cardId={card.id} picked={version} onPick={setVersion} />
      </div>

      <div className="flex flex-wrap gap-2.5">
        <Field label="Idioma" className="flex-1">
          <Select size="field" options={meta.languages} value={language} onChange={setLanguage} />
        </Field>
        <Field label="Cantidad" className="w-22.5">
          <Input
            type="number"
            min={1}
            inputMode="numeric"
            value={quantity}
            onChange={(event) => setQuantity(Number(event.target.value))}
          />
        </Field>
      </div>

      <div>
        <FieldLabel>Condición</FieldLabel>
        <ChipGroup
          layout="loose"
          size="md"
          value={condition}
          onChange={setCondition}
          options={meta.conditions.map((option) => ({
            value: option.key,
            label: option.key,
            title: option.label,
          }))}
        />
      </div>

      <div className="mt-1 flex flex-wrap gap-2">
        <Button type="submit" variant="primary" disabled={add.isPending}>
          Guardar
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}
