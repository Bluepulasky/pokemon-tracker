/* Rendering helpers shared by the views. */

export const el = (html) => {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const eur = (n) => n == null ? '—'
  : new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR',
      maximumFractionDigits: n >= 100 ? 0 : 2 }).format(n);

export const pct = (n) => `${(n ?? 0).toFixed(1).replace('.0', '')}%`;

export function toast(msg, isError = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' err' : '');
  t.hidden = false;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.hidden = true; }, 3200);
}

/* Catalog art: prefer the locally cached copy so the grid does not depend on a
   third-party CDN on every page load (PLAN.md §2.14). */
export function cardArt(card) {
  if (card.image_local) return `/media/${card.image_local}`;
  return card.image_small_url || '';
}

export function photoUrl(photo, thumb = true) {
  const f = thumb && photo.thumb_filename ? photo.thumb_filename : photo.filename;
  return `/media/${f}`;
}

/* A missing card renders as markup, never as a downloaded image. */
export function placeholder(number, setCode) {
  return `<div class="placeholder">
    <div class="n">#${esc(number || '?')}</div>
    <div class="s">${esc(setCode || '')}</div>
  </div>`;
}

/* Hall of Fame badge. 0 is "unranked", so it renders nothing at all rather than
   a zero — a grid full of "0" badges would be noise. */
export function hofBadge(rating, { compact = false } = {}) {
  const r = Number(rating) || 0;
  if (!r) return '';
  const tier = r >= 7 ? ' top' : r >= 5 ? ' fav' : '';
  return `<span class="hof${tier}${compact ? ' sm' : ''}" title="Hall of Fame ${r}/8">★${r}</span>`;
}

export function progressBar(owned, target) {
  const p = target ? (100 * owned / target) : 0;
  return `<div class="bar${p >= 100 ? ' good' : ''}"><i style="width:${Math.min(100, p)}%"></i></div>`;
}

/* Minimal inline SVG line chart — no charting library, no external requests. */
export function lineChart(points, { height = 180, format = eur } = {}) {
  if (!points.length) return '<div class="empty">Sin histórico todavía.</div>';
  if (points.length === 1) points = [points[0], points[0]];
  const W = 600, H = height, P = 26;
  const ys = points.map((p) => p.value);
  const min = Math.min(...ys), max = Math.max(...ys);
  const span = max - min;
  const x = (i) => P + (i * (W - P * 2)) / (points.length - 1);
  // A flat series (or a single snapshot) would otherwise sit on the axis and read
  // as zero; centre it instead so the value label matches what is drawn.
  const y = (v) => span ? H - P - ((v - min) / span) * (H - P * 2) : H / 2;
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const area = `${line} L${x(points.length - 1).toFixed(1)},${H - P} L${x(0).toFixed(1)},${H - P} Z`;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="grad" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stop-color="#ffcb05" stop-opacity=".28"/>
      <stop offset="100%" stop-color="#ffcb05" stop-opacity="0"/>
    </linearGradient></defs>
    <line class="axis" x1="${P}" y1="${H - P}" x2="${W - P}" y2="${H - P}"/>
    <path class="area" d="${area}"/><path class="line" d="${line}"/>
    <text x="${P}" y="14">${esc(format(max))}</text>
    <text x="${P}" y="${H - 8}">${esc(points[0].label)}</text>
    <text x="${W - P}" y="${H - 8}" text-anchor="end">${esc(points[points.length - 1].label)}</text>
  </svg>`;
}
