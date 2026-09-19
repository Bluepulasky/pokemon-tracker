/* Shapes of the JSON the Flask API returns. Only the fields the UI reads. */

export interface Option {
  key: string;
  label: string;
}

export interface LanguageOption extends Option {
  multiplier?: number;
}

export interface RatingOption {
  value: number;
  label: string;
}

export interface Meta {
  version?: string;
  conditions: Option[];
  variants: Option[];
  languages: LanguageOption[];
  editions: Option[];
  rarities: string[];
  types: string[];
  energy_types?: string[];
  ratings: RatingOption[];
}

export interface CardImageSource {
  image_local?: string | null;
  image_small_url?: string | null;
}

export interface Photo {
  id: number;
  filename: string;
  thumb_filename?: string | null;
  is_primary?: boolean | number;
}

/* ------------------------------------------------------------------ sets */

export interface SetProgress {
  id: string;
  name: string;
  logo_url?: string | null;
  series?: string | null;
  owned: number;
  target: number;
  completion_pct: number;
  missing?: number;
}

export interface SetCardEntry extends CardImageSource {
  id: string;
  name: string;
  number: string;
  number_sort: number | null;
  rarity: string | null;
  official_set_id: string;
  owned_qty: number;
  collecting: number | boolean;
}

export interface SetDetail {
  id: string;
  name: string;
  loose_completion: boolean;
  progress?: SetProgress;
  cards: SetCardEntry[];
}

export interface MissingRow extends CardImageSource {
  card_id: string;
  label: string | null;
  number: string;
  rarity: string | null;
  held: number;
  target: number;
  still_needed: number;
  missing_entirely: number | boolean;
}

export interface HiddenSet {
  id: string;
  name: string;
  logo_url?: string | null;
}

/* ------------------------------------------------------------- dashboard */

export interface TopValueRow {
  card_id: string;
  name: string;
  variant: string;
  condition: string;
  quantity: number;
  value: number;
}

export interface Dashboard {
  value: { total_eur: number; unpriced_items: number };
  unique_cards: number;
  physical_cards: number;
  unique_pokemon?: number;
  sets_total: number;
  sets_complete: number;
  completion_pct: number;
  owned_cards: number;
  target_cards: number;
  copies_pct: number;
  copies_held: number;
  copies_target: number;
  most_complete: SetProgress[];
  most_missing: SetProgress[];
  top_value: TopValueRow[];
  last_price_refresh: string | null;
}

export interface Snapshot {
  captured_on: string;
  value_eur: number;
}

/* ------------------------------------------------------------ collection */

export interface ItemValue {
  total?: number | null;
  unit?: number | null;
  base?: number | null;
  basis?: string;
  manual?: boolean;
  partial?: boolean;
  condition_multiplier?: number;
  language_multiplier?: number;
}

export interface CollectionItem extends CardImageSource {
  id: number;
  card_id: string;
  name?: string;
  label?: string;
  number?: string;
  official_set_id?: string;
  set_code?: string;
  printing_name?: string;
  variant: string;
  condition: string;
  language: string;
  quantity: number;
  first_edition: number | boolean;
  market_url?: string | null;
  rating?: number;
  photos: Photo[];
  display_photo?: Photo | null;
  value?: ItemValue;
  /* Cartas-view extras */
  owned?: boolean;
  group_quantity?: number;
  group_card_ids?: string[];
  reprint_owned?: boolean;
}

export interface CollectionTotals {
  unique_cards: number;
  physical_cards: number;
  item_rows: number;
  slots?: number;
  owned_slots?: number;
}

export interface CollectionPage {
  data: CollectionItem[];
  total: number;
  page: number;
  totals: CollectionTotals;
}

export type CollectionFilters = Record<string, string>;

export interface NewItem {
  card_id: string;
  language: string;
  condition: string;
  quantity: number;
  market_product_id: number;
}

export interface ItemPatch {
  first_edition: boolean;
  condition: string;
  language: string;
  quantity: number;
}

/* ----------------------------------------------------------------- cards */

export interface CardDetail extends CardImageSource {
  id: string;
  name: string;
  number: string;
  rarity: string | null;
  artist: string | null;
  set_name: string;
  market_url?: string | null;
  rating: number;
  target: number;
}

export interface SearchCard extends CardImageSource {
  id: string;
  name: string;
  number: string;
  set_name: string;
}

export interface SearchResult {
  cards: SearchCard[];
  collection: { card_id: string }[];
}

export interface CardVersion {
  market_product_id: number;
  card_id: string | null;
  code: string | null;
  set: string | null;
  version: string | null;
  rarity: string | null;
  image: string | null;
  price: number | null;
  is_current: boolean;
}

export interface Quote {
  provider: string;
  market: string;
  price: number | null;
  currency: string;
  trusted: boolean;
}

/* ----------------------------------------------------------- maintenance */

export interface Budget {
  provider: string;
  limit: number;
  used: number;
  remaining: number;
  window_hours: number;
}

export interface JobStatus {
  status: 'idle' | 'running' | 'done' | 'failed';
  name: string | null;
  started_at: string | null;
  error: string | null;
  result: unknown;
  budgets?: Budget[];
}

/** `{ condition: { "M/NM": 1, "EX": 0.8, … } }` */
export type Modifiers = Record<string, Record<string, number>>;

export interface HealthFinding {
  level: 'error' | 'warning' | 'info';
  message: string;
  detail: string[];
}

export interface Episode {
  id: number;
  name: string;
  code: string | null;
  logo: string | null;
  released_at: string | null;
  cards_total: number;
  products: number;
  imported: boolean;
  empty?: boolean;
}

export interface EpisodeImportResult {
  name: string;
  cards: number;
  requests: number;
}

export interface TargetImportResult {
  updated: number;
  unchanged: number;
  errors: number;
  changes?: { card_id: string; from: number; to: number }[];
  problems?: { line: number; card_id?: string; error: string }[];
}

export interface CardMetaResult {
  overwrite: boolean;
  changed?: Record<string, number>;
  unknown: number;
  unknown_ids?: string[];
}
