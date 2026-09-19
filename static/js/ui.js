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
   third-party CDN on every page load. */
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

export function lineChart(points, { height = 200, format = eur } = {}) {
  if (!points.length) return '<div class="empty">Sin histórico todavía.</div>';
  const id = 'chart-' + Math.random().toString(36).slice(2);
  // Guardamos para inicializar después del render
  lineChart._pending = lineChart._pending || {};
  lineChart._pending[id] = { points, format };
  return `<div style="height:${height}px"><canvas id="${id}"></canvas></div>`;
}

lineChart.init = function () {
  for (const [id, { points: pts, format }] of Object.entries(lineChart._pending || {})) {
    const canvas = document.getElementById(id);
    if (!canvas) continue;
    const fmt = (v) => '€' + Math.round(v).toLocaleString('es-ES');
    const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
    const fmtLabel = (s) => {
      const [m, d] = s.split('-');
      return `${d} ${MESES[parseInt(m, 10) - 1]}`;
    };
    const fmtAxis = (val, idx) => {
      const [m] = pts[idx].label.split('-');
      return `${MESES[parseInt(m, 10) - 1]} ${pts[idx].year}`;
    };

    new Chart(canvas, {
      type: 'line',
      data: {
        labels: pts.map((p) => p.label),
        datasets: [{
          data: pts.map((p) => p.value),
          borderColor: '#ffcb05',
          backgroundColor: 'rgba(255,203,5,0.15)',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointBackgroundColor: '#ffcb05',
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => fmtLabel(items[0].label),
              label: (ctx) => fmt(ctx.parsed.y),
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: { color: '#888', callback: fmtAxis },
          },
          y: {
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: { color: '#888', callback: (v) => fmt(v) },
          },
        },
      },
    });
    delete lineChart._pending[id];
  }
};
