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
  rate:        (id, rating)   => req('PUT', `/api/collection/${id}`, { rating }),
  byCard:      (cardId)       => req('GET', `/api/collection/by-card/${cardId}`),
  addItem:     (b)            => req('POST', '/api/collection', b),
  updateItem:  (id, b)        => req('PUT', `/api/collection/${id}`, b),
  deleteItem:  (id)           => req('DELETE', `/api/collection/${id}`),
  uploadPhoto: (id, file)     => { const fd = new FormData(); fd.append('photo', file);
                                   return req('POST', `/api/collection/${id}/photos`, fd, true); },
  deletePhoto: (id)           => req('DELETE', `/api/collection/photos/${id}`),
  setPrimary:  (id)           => req('PUT', `/api/collection/photos/${id}`, { is_primary: true }),
  refreshPrices: ()           => req('POST', '/api/prices/refresh', {}),
};
