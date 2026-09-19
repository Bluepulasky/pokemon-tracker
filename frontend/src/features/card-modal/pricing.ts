import type { CollectionItem } from '@/api/types';
import { cents } from '@/lib/format';

const FIRST_EDITION_FACTOR = 2;

/**
 * The printing's price before grade, language and first-edition multipliers,
 * worked back from the stored unit price. `null` when the copy is unpriced.
 */
export function basePrice(item: CollectionItem): number | null {
  const value = item.value;
  if (value?.unit == null) return null;
  const condition = value.condition_multiplier ?? 1;
  const language = value.language_multiplier ?? 1;
  const edition = item.first_edition ? FIRST_EDITION_FACTOR : 1;
  return value.unit / condition / language / edition;
}

interface PreviewInput {
  base: number;
  conditionMultiplier: number;
  languageMultiplier: number;
  firstEdition: boolean;
  quantity: number;
}

/** Unit and total, rounded where the backend rounds: the unit first, the total from it. */
export function previewPrice(input: PreviewInput): { unit: number; total: number } {
  const edition = input.firstEdition ? FIRST_EDITION_FACTOR : 1;
  const unit = cents(input.base * input.conditionMultiplier * input.languageMultiplier * edition);
  return { unit, total: cents(unit * input.quantity) };
}
