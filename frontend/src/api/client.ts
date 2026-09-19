/* Thin API client. Every response goes through the same error envelope. */
import type {
  CardDetail,
  CardMetaResult,
  CardVersion,
  CollectionFilters,
  CollectionItem,
  CollectionPage,
  Dashboard,
  Episode,
  EpisodeImportResult,
  HealthFinding,
  HiddenSet,
  ItemPatch,
  JobStatus,
  Meta,
  MissingRow,
  Modifiers,
  NewItem,
  Quote,
  SearchResult,
  SetDetail,
  SetProgress,
  Snapshot,
  TargetImportResult,
} from './types';

interface ErrorEnvelope {
  error?: { message?: string } | string;
}

function errorMessage(data: unknown, status: number): string {
  const error = (data as ErrorEnvelope | null)?.error;
  if (typeof error === 'string') return error;
  return error?.message ?? `HTTP ${status}`;
}

/** Parses a response body; an empty body is `null`. */
function parseJson(text: string, status: number): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error(`HTTP ${status}: respuesta no válida`);
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE';

/** Sends one request. `body` is JSON-encoded unless it is already a FormData. */
async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = localStorage.getItem('app_token');
  if (token) headers['X-App-Token'] = token;

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  const res = await fetch(path, { method, headers, body: payload });
  const data = parseJson(await res.text(), res.status);
  if (!res.ok) throw new Error(errorMessage(data, res.status));
  return data as T;
}

const get = <T>(path: string) => request<T>('GET', path);
const post = <T>(path: string, body: unknown = {}) => request<T>('POST', path, body);
const put = <T>(path: string, body: unknown) => request<T>('PUT', path, body);
const del = <T>(path: string) => request<T>('DELETE', path);

/** `{a: 1, b: ''}` → `a=1`. Blank and null values are left out. */
function queryString(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== '' && value != null) search.set(key, String(value));
  }
  return search.toString();
}

function fileForm(field: string, file: File): FormData {
  const form = new FormData();
  form.append(field, file);
  return form;
}

const enc = encodeURIComponent;
const overwriteFlag = (overwrite: boolean) => (overwrite ? '?overwrite=1' : '');

interface List<T> {
  data: T[];
}

export const api = {
  meta: () => get<Meta>('/api/meta'),
  dashboard: () => get<Dashboard>('/api/dashboard'),
  history: () => get<List<Snapshot>>('/api/stats/history'),
  search: (q: string) => get<SearchResult>(`/api/search?q=${enc(q)}`),

  sets: () => get<List<SetProgress>>('/api/sets'),
  set: (id: string) => get<SetDetail>(`/api/sets/${id}`),
  missing: (id: string, sort: string) =>
    get<List<MissingRow>>(`/api/sets/${id}/missing?sort=${enc(sort)}`),
  setCardInSet: (setId: string, cardId: string, action: 'keep' | 'drop') =>
    put<unknown>(`/api/sets/${setId}/card/${cardId}`, { action }),
  setHidden: (setId: string, hidden: boolean) =>
    put<unknown>(`/api/sets/${setId}/hidden`, { hidden }),
  setLoose: (setId: string, enabled: boolean) =>
    put<unknown>(`/api/sets/${setId}/loose`, { enabled }),
  hiddenSets: () => get<List<HiddenSet>>('/api/maintenance/hidden-sets'),

  card: (id: string) => get<CardDetail>(`/api/cards/${id}`),
  rateCard: (cardId: string, rating: number) =>
    put<unknown>(`/api/cards/${cardId}/rating`, { rating }),
  setTarget: (cardId: string, target: number) =>
    put<unknown>(`/api/cards/${cardId}/target`, { target }),
  versions: (cardId: string) =>
    get<{ versions: CardVersion[] }>(`/api/prices/versions?card_id=${enc(cardId)}`),
  quotes: (cardId: string, variant: string) =>
    get<{ quotes: Quote[] }>(
      `/api/prices/${cardId}/quotes${variant ? `?variant=${enc(variant)}` : ''}`,
    ),

  collection: (filters: CollectionFilters) =>
    get<CollectionPage>(`/api/collection?${queryString(filters)}`),
  itemsByCard: (cardId: string, reprints: boolean) =>
    get<List<CollectionItem>>(`/api/collection/by-card/${cardId}${reprints ? '?reprints=1' : ''}`),
  addItem: (item: NewItem) => post<unknown>('/api/collection', item),
  updateItem: (id: number, patch: ItemPatch) => put<unknown>(`/api/collection/${id}`, patch),
  deleteItem: (id: number) => del<unknown>(`/api/collection/${id}`),
  uploadPhoto: (itemId: number, file: File) =>
    post<unknown>(`/api/collection/${itemId}/photos`, fileForm('photo', file)),
  setPrimaryPhoto: (photoId: number) =>
    put<unknown>(`/api/collection/photos/${photoId}`, { is_primary: true }),

  refreshPrices: () => post<{ updated: number; unpriced: number }>('/api/prices/refresh'),
  refreshPricesAsync: () => post<JobStatus>('/api/prices/refresh-async'),
  modifiers: () => get<Modifiers>('/api/prices/modifiers'),
  setModifier: (kind: string, key: string, multiplier: number) =>
    put<unknown>(`/api/prices/modifiers/${kind}/${key}`, { multiplier }),
  setManualPrice: (cardId: string, variant: string, price: number | null) =>
    put<unknown>(`/api/prices/manual/${cardId}/${variant}`, { price }),

  jobStatus: () => get<JobStatus>('/api/maintenance/status'),
  syncCatalog: () => post<{ synced: number }>('/api/maintenance/sync-catalog'),
  health: () => get<{ findings: HealthFinding[] }>('/api/maintenance/health'),
  episodes: (q: string) =>
    get<{ episodes: Episode[] }>(`/api/maintenance/episodes${q ? `?q=${enc(q)}` : ''}`),
  importEpisode: (id: number) =>
    post<EpisodeImportResult>(`/api/maintenance/episodes/${id}/import`),

  importTargets: (file: File) =>
    post<TargetImportResult>('/api/maintenance/targets/import', fileForm('file', file)),
  applyCardMeta: (overwrite: boolean) =>
    post<CardMetaResult>(`/api/maintenance/card-meta/apply${overwriteFlag(overwrite)}`),
  importCardMeta: (file: File, overwrite: boolean) =>
    post<CardMetaResult>(
      `/api/maintenance/card-meta/import${overwriteFlag(overwrite)}`,
      fileForm('file', file),
    ),

  targetsExportUrl: '/api/maintenance/targets/export',
  cardMetaExportUrl: '/api/maintenance/card-meta/export',
} as const;
