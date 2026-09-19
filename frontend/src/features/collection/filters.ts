import type { Meta, Option, SetProgress } from '@/api/types';
import { toOptions } from '@/components/ui/controls';

/** Filters that are a plain select in the toolbar, in display order. */
export const SELECT_FILTERS = [
  'set',
  'condition',
  'variant',
  'language',
  'rarity',
  'rating',
  'type',
  'color',
  'edition',
  'min_quantity',
] as const;

export type SelectFilter = (typeof SELECT_FILTERS)[number];

/** Every filter the Cartas URL can carry, with the value it has when absent. */
export const FILTER_DEFAULTS = {
  ...(Object.fromEntries(SELECT_FILTERS.map((key) => [key, ''])) as Record<SelectFilter, string>),
  q: '',
  sort: 'set',
  rating_min: '',
  show_all: '',
  unique_reprints: '',
};

export type FilterKey = keyof typeof FILTER_DEFAULTS;

export const SORT_OPTIONS: Option[] = [
  { key: 'set', label: 'Por set' },
  { key: 'name', label: 'Por nombre' },
  { key: 'number', label: 'Por número' },
  { key: 'rarity', label: 'Por rareza' },
  { key: 'quantity', label: 'Por cantidad' },
  { key: 'rating', label: 'Por Hall of Fame' },
  { key: 'recent', label: 'Más recientes' },
];

interface SelectSpec {
  placeholder: string;
  options: Option[];
}

/** Placeholder and options of each select filter. */
export function selectSpecs(meta: Meta, sets: SetProgress[]): Record<SelectFilter, SelectSpec> {
  return {
    set: {
      placeholder: 'Todos los sets',
      options: sets.map((set) => ({ key: set.id, label: set.name })),
    },
    condition: { placeholder: 'Condición', options: meta.conditions },
    variant: { placeholder: 'Variante', options: meta.variants },
    language: { placeholder: 'Idioma', options: meta.languages },
    rarity: { placeholder: 'Rareza', options: toOptions(meta.rarities) },
    rating: {
      placeholder: 'Hall of Fame',
      options: [
        { key: '0', label: 'Sin rating' },
        ...meta.ratings
          .filter((rating) => rating.value > 0)
          .map((rating) => ({ key: String(rating.value), label: `★ ${rating.value}` })),
      ],
    },
    type: { placeholder: 'Supertipo', options: toOptions(meta.types) },
    color: { placeholder: 'Color', options: toOptions(meta.energy_types ?? []) },
    edition: { placeholder: 'Edición', options: meta.editions },
    min_quantity: {
      placeholder: 'Cantidad',
      options: [1, 2, 3, 4, 5].map((n) => ({ key: String(n), label: `${n} o más` })),
    },
  };
}
