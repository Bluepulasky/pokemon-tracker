/* Thin API client. Every response goes through the same error envelope. */

const TOKEN = localStorage.getItem('app_token') || '';

async function req(method, path, body, isForm = false) {
  const opts = { method, headers: {} };
  if (TOKEN) opts.headers['X-App-Token'] = TOKEN;
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  }
  const res = await fetch(path, opts);
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(data?.error?.message || `HTTP ${res.status}`);
  return data;
}

const qs = (o) => Object.entries(o)
  .filter(([, v]) => v !== '' && v != null)
  .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');

export const api = {
  meta:        ()             => req('GET', '/api/meta'),
  dashboard:   ()             => req('GET', '/api/dashboard'),
  history:     ()             => req('GET', '/api/stats/history'),
  sets:        ()             => req('GET', '/api/sets'),
  set:         (id)           => req('GET', `/api/sets/${id}`),
  missing:     (id, sort)     => req('GET', `/api/sets/${id}/missing?sort=${sort || 'number'}`),
  rebuildSet:  (id)           => req('POST', `/api/sets/${id}/rebuild`),
  card:        (id)           => req('GET', `/api/cards/${id}`),
  search:      (q)            => req('GET', `/api/search?q=${encodeURIComponent(q)}`),
  collection:  (f)            => req('GET', `/api/collection?${qs(f || {})}`),
  rateCard:    (cardId, rating) => req('PUT', `/api/cards/${cardId}/rating`, { rating }),
  setTarget:   (cardId, target) => req('PUT', `/api/cards/${cardId}/target`, { target }),
  byCard:      (cardId)       => req('GET', `/api/collection/by-card/${cardId}`),
  addItem:     (b)            => req('POST', '/api/collection', b),
  updateItem:  (id, b)        => req('PUT', `/api/collection/${id}`, b),
  deleteItem:  (id)           => req('DELETE', `/api/collection/${id}`),
  uploadPhoto: (id, file)     => { const fd = new FormData(); fd.append('photo', file);
                                   return req('POST', `/api/collection/${id}/photos`, fd, true); },
  deletePhoto: (id)           => req('DELETE', `/api/collection/photos/${id}`),
  setPrimary:  (id)           => req('PUT', `/api/collection/photos/${id}`, { is_primary: true }),
  refreshPrices: ()           => req('POST', '/api/prices/refresh', {}),
  refreshAsync: ()            => req('POST', '/api/prices/refresh-async', {}),
  rebuildDb:    ()            => req('POST', '/api/maintenance/rebuild', {}),
  jobStatus:    ()            => req('GET', '/api/maintenance/status'),
  modifiers:    ()            => req('GET', '/api/prices/modifiers'),
  getSetMode:   (setId)        => req('GET', `/api/sets/${setId}/mode`),
  setSetMode:   (setId, mode)  => req('PUT', `/api/sets/${setId}/mode`, { mode }),
  health:       ()            => req('GET', '/api/maintenance/health'),
  episodes:     (q)           => req('GET', '/api/maintenance/episodes'
                                   + (q ? `?q=${encodeURIComponent(q)}` : '')),
  importEpisode:(id)          => req('POST', `/api/maintenance/episodes/${id}/import`, {}),
  versions:     (cardId)      => req('GET', `/api/prices/versions?card_id=${encodeURIComponent(cardId)}`),
  quotes:       (cardId, variant) =>
                                 req('GET', `/api/prices/${cardId}/quotes` + (variant ? `?variant=${encodeURIComponent(variant)}` : '')),
  importTargets: (file) => {
    const body = new FormData();
    body.append('file', file);
    return fetch('/api/maintenance/targets/import', { method: 'POST', body })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
        return data;
      });
  },
  exportTargetsUrl: (setId) =>
    '/api/maintenance/targets/export' + (setId ? `?set_id=${encodeURIComponent(setId)}` : ''),
  setModifier:  (kind, key, multiplier) =>
                                 req('PUT', `/api/prices/modifiers/${kind}/${key}`, { multiplier }),
  setManualPrice: (cardId, variant, price) =>
                                 req('PUT', `/api/prices/manual/${cardId}/${variant}`, { price }),
};
