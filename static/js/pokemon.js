/* SPA shell: hash routing + the four views. */

import { api } from './api.js';
import { closeModal, initModal, openCard } from './modal.js';
import { cardArt, el, esc, eur, hofBadge, lineChart, pct, photoUrl, placeholder,
         progressBar, toast } from './ui.js';

const view = () => document.getElementById('view');
let META = null;

/* ------------------------------------------------------------------ boot */
async function boot() {
  try {
    META = await api.meta();
  } catch (e) {
    view().innerHTML = `<div class="empty">No se pudo contactar con la API.<br><small>${esc(e.message)}</small></div>`;
    return;
  }
  initModal(META, () => render(true));
  stampVersion();
  wireSearch();
  // A route change must dismiss the modal, or it lingers over the new view.
  window.addEventListener('hashchange', () => { closeModal(); render(); });
  render();
}

/* Which build is being served. Without it, "it still shows the old price" is
   ambiguous between a bug and an image that was never rebuilt. */
function stampVersion() {
  if (!META.version) return;
  const el = document.createElement('span');
  el.className = 'build-stamp';
  el.textContent = META.version;
  el.title = 'Build en ejecución';
  document.querySelector('.topbar')?.appendChild(el);
}

function route() {
  const [path, query] = (location.hash.slice(2) || 'dashboard').split('?');
  const parts = path.split('/').filter(Boolean);
  return { name: parts[0] || 'dashboard', id: parts[1], params: new URLSearchParams(query || '') };
}

const VIEWS = { dashboard, sets, set: setDetail, cartas: collection,
                collection, missing, mantenimiento };   // /collection kept as an alias

async function render(keepScroll = false) {
  const r = route();
  document.querySelectorAll('.tabs a').forEach((a) => a.classList.toggle(
    'active', a.dataset.tab === r.name
      || (r.name === 'set' && a.dataset.tab === 'sets')
      || (r.name === 'collection' && a.dataset.tab === 'cartas')));
  const y = keepScroll ? window.scrollY : 0;
  const fn = VIEWS[r.name] || dashboard;
  view().innerHTML = '<div class="loading">Cargando…</div>';
  try {
    await fn(r);
  } catch (e) {
    view().innerHTML = `<div class="empty">Error: ${esc(e.message)}</div>`;
  }
  window.scrollTo(0, y);
}

/* ------------------------------------------------------------- dashboard */
async function dashboard() {
  const [d, hist] = await Promise.all([api.dashboard(), api.history()]);
  const v = d.value;
  const points = hist.data.map((s) => ({ label: s.captured_on.slice(5), value: s.value_eur }));

  view().innerHTML = `
    <h1>Mi colección</h1>
    <p class="sub">${d.unique_cards} cartas únicas · ${d.physical_cards} cartas físicas ·
       ${d.sets_total} sets · ${pct(d.completion_pct)} únicas · ${pct(d.copies_pct)} copias</p>

    <div class="stat-grid">
      <div class="stat accent"><div class="k">Valor estimado</div>
        <div class="v">${esc(eur(v.total_eur))}</div>
        ${v.unpriced_items ? `<div class="note">${v.unpriced_items} sin precio conocido</div>` : ''}</div>
      <div class="stat"><div class="k">Cartas únicas</div><div class="v">${d.unique_cards}</div></div>
      <div class="stat"><div class="k">Cartas físicas</div><div class="v">${d.physical_cards}</div></div>
      <div class="stat"><div class="k">Sets completos</div>
        <div class="v">${d.sets_complete}<small> / ${d.sets_total}</small></div></div>
      <div class="stat"><div class="k">Completitud (únicas)</div>
        <div class="v">${pct(d.completion_pct)}</div>
        ${progressBar(d.owned_cards, d.target_cards)}
        <div class="note">${d.owned_cards} / ${d.target_cards} cartas distintas</div></div>
      <div class="stat"><div class="k">Completitud (copias)</div>
        <div class="v">${pct(d.copies_pct)}</div>
        ${progressBar(d.copies_held, d.copies_target)}
        <div class="note">${d.copies_held} / ${d.copies_target} copias objetivo</div></div>
    </div>

    <h2 style="margin-top: 16px;">Evolución del valor</h2>
    ${lineChart(points)}
    ${points.length < 2 ? '<div class="note">El histórico se acumula con cada snapshot mensual.</div>' : ''}

    <h2 style="margin-top: 16px;">Sets más completos</h2>
    <div class="set-grid">${d.most_complete.map(setCardHtml).join('')}</div>

    <h2 style="margin-top: 16px;">Sets con más cartas faltantes</h2>
    <div class="set-grid">${d.most_missing.map(setCardHtml).join('')}</div>

    <h2 style="margin-top: 16px;">Cartas de mayor valor</h2>
    <div class="missing-list">${
      d.top_value.length ? d.top_value.map((t) => `
        <div class="missing-row" data-card="${esc(t.card_id)}">
          <span class="n">#${esc(t.number)}</span>
          <span>${esc(t.name)}</span>
          <span class="tag">${esc(t.variant)} · ${esc(t.condition)} · ×${t.quantity}</span>
          <span class="r">${esc(eur(t.value))}</span>
        </div>`).join('')
      : '<div class="empty">Todavía no hay precios. Ejecuta una actualización de precios.</div>'}</div>

    <div class="btn-row">
      <button class="btn" id="refresh-prices">Actualizar precios ahora</button>
      <span class="note" style="align-self:center">
        Última actualización: ${esc(d.last_price_refresh || 'nunca')}</span>
    </div>`;

  wireCardClicks();
  view().querySelectorAll('[data-set]').forEach((n) => {
    n.onclick = () => { location.hash = `#/set/${n.dataset.set}`; };
  });
  view().querySelector('#refresh-prices').onclick = async (e) => {
    e.target.disabled = true;
    e.target.textContent = 'Actualizando…';
    try {
      const r = await api.refreshPrices();
      toast(`${r.updated} precios actualizados${r.unpriced ? `, ${r.unpriced} sin datos` : ''}`);
      render();
    } catch (err) {
      toast(err.message, true);
      e.target.disabled = false;
      e.target.textContent = 'Actualizar precios ahora';
    }
  };
}

const setCardHtml = (s) => `
  <div class="set-card" data-set="${esc(s.id)}">
    <button class="set-hide" data-hide="${esc(s.id)}"
            title="Ocultar de la colección (se puede mostrar desde Mantenimiento)">×</button>
    <span class="pct">${pct(s.completion_pct)}</span>
    ${s.logo_url ? `<img class="set-logo" src="${esc(s.logo_url)}" alt="" loading="lazy">` : ''}
    <div class="name">${esc(s.name)}</div>
    <div class="count">${s.owned} / ${s.target} cartas${
      s.missing ? ` · faltan ${s.missing}` : ''}</div>
    ${progressBar(s.owned, s.target)}
  </div>`;

/* ------------------------------------------------------------------ sets */
async function sets() {
  const { data } = await api.sets();
  // Grouped by TCG series/era (Base / Gym / Neo / … / Scarlet & Violet), which
  // the API derives from each set's release date. `data` is already ordered by
  // release date, so the groups fall out oldest-first and each era's sets stay
  // contiguous. A set with no date (so no era) collects under "Otros".
  const groups = {};
  for (const s of data) (groups[s.series || 'Otros'] ||= []).push(s);

  view().innerHTML = `
    <h1>Sets</h1>
    <p class="sub">${data.length} sets personalizados ·
       ${data.reduce((a, s) => a + s.owned, 0)} / ${data.reduce((a, s) => a + s.target, 0)} cartas</p>
    ${Object.entries(groups).map(([g, list]) => `
      <h2>${esc(g)}</h2>
      <div class="set-grid">${list.map((s) => setCardHtml({
        ...s, missing: s.target - s.owned })).join('')}</div>`).join('')}`;

  view().querySelectorAll('[data-set]').forEach((n) => {
    n.onclick = () => { location.hash = `#/set/${n.dataset.set}`; };
  });
  // The X hides the set from the collection. It keeps the data, so it is not a
  // delete and needs no confirm — un-hiding lives in Mantenimiento.
  view().querySelectorAll('[data-hide]').forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      try {
        await api.setHidden(btn.dataset.hide, true);
        toast('Set oculto. Se muestra de nuevo desde Mantenimiento.');
        sets();
      } catch (err) { toast(err.message, true); }
    };
  });
}

/* ------------------------------------------------------- set detail grid */
async function setDetail(r) {
  const [s, { data: allSets }] = await Promise.all([api.set(r.id), api.sets()]);
  const idx = allSets.findIndex((x) => String(x.id) === String(r.id));
  const prev = allSets[idx - 1] ?? null;
  const next = allSets[idx + 1] ?? null;
  const p = s.progress || { owned: 0, target: 0, completion_pct: 0 };
  const sort = r.params.get('sort') || 'number';
  const rar = r.params.get('rar') || 'all';       // all | holo | no-holo (view)
  const own = r.params.get('own') || 'all';       // all | owned | missing (view)
  const col = r.params.get('col') || 'collecting'; // all | collecting | not (view)

  const isHolo = (c) => /holo/i.test(c.rarity || '');
  // Every card in the set, each tagged collecting/owned. The set is a checklist
  // of the whole thing; the toggle on each card says whether it counts.
  const cards = (s.cards || []).map((c) => ({
    card_id: c.id, label: c.name, name: c.name, number: c.number,
    number_sort: c.number_sort, rarity: c.rarity,
    image_small_url: c.image_small_url, image_local: c.image_local,
    official_set_id: c.official_set_id,
    owned: (c.owned_qty || 0) > 0, quantity: c.owned_qty || 0,
    collecting: !!c.collecting, holo: isHolo(c),
  }));

  let shown = cards;
  if (rar === 'holo') shown = shown.filter((c) => c.holo);
  if (rar === 'no-holo') shown = shown.filter((c) => !c.holo);
  if (own === 'owned') shown = shown.filter((c) => c.owned);
  if (own === 'missing') shown = shown.filter((c) => !c.owned);
  if (col === 'collecting') shown = shown.filter((c) => c.collecting);
  if (col === 'not') shown = shown.filter((c) => !c.collecting);
  shown = [...shown].sort(sorter(sort));

  const collecting = cards.filter((c) => c.collecting).length;

  view().innerHTML = `
    <div class="set-nav-row">
      <div class="set-nav-side left">
        ${prev ? `<button class="set-nav" data-set="${prev.id}">‹‹ ${esc(prev.name)}</button>` : ''}
      </div>
      <div class="set-nav-center">
        <h1>${esc(s.name)}</h1>
        <p class="sub">Coleccionando ${collecting} de ${cards.length} · tenés ${p.owned}
          · falta ${Math.max(0, collecting - p.owned)}</p>
      </div>
      <div class="set-nav-side right">
        ${next ? `<button class="set-nav" data-set="${next.id}">${esc(next.name)} ››</button>` : ''}
      </div>
    </div>
    ${progressBar(p.owned, collecting)}

    <label class="loose-toggle" title="Una carta de este set cuenta como poseída si tenés cualquier reimpresión suya de otro set.">
      <input type="checkbox" id="loose-toggle" ${s.loose_completion ? 'checked' : ''}>
      <span>Cualquier versión cuenta para el progreso <em>(experimental)</em></span>
    </label>

    <div class="quick-select" id="q-collect">
      <span class="qs-label">Coleccionar ★</span>
      ${[['all', 'Todo'], ['holo', 'Solo holo'], ['non-holo', 'Solo no holo'],
         ['none', 'Ninguno'], ['invert', 'Invertir']]
.map(([k, l]) => `<button class="qs-btn" data-collect="${k}">${l}</button>`).join('')}
    </div>

    <div class="toolbar">
      <div class="chips seg" id="f-rar">
        ${[['all', 'Todas'], ['holo', 'Holo'], ['no-holo', 'No holo']]
.map(([k, l]) => `<span class="chip${rar === k ? ' on' : ''}" data-rar="${k}">${l}</span>`).join('')}
      </div>
      <div class="chips seg" id="f-own">
        ${[['all', 'Todas'], ['owned', 'Poseídas'], ['missing', 'Faltantes']]
.map(([k, l]) => `<span class="chip${own === k ? ' on' : ''}" data-own="${k}">${l}</span>`).join('')}
      </div>
      <div class="chips seg" id="f-col">
        ${[['all', 'Todas'], ['collecting', 'Coleccionando'], ['not', 'No coleccionando']]
.map(([k, l]) => `<span class="chip${col === k ? ' on' : ''}" data-col="${k}">${l}</span>`).join('')}
      </div>
      <select id="f-sort">
        <option value="number"${sort === 'number' ? ' selected' : ''}>Por número</option>
        <option value="name"${sort === 'name' ? ' selected' : ''}>Por nombre</option>
        <option value="rarity"${sort === 'rarity' ? ' selected' : ''}>Por rareza</option>
      </select>
      <span class="spacer">${shown.length} cartas</span>
    </div>

    <div class="card-grid">${shown.map(cardCheckHtml).join('')}</div>`;
  view().querySelectorAll('.set-nav').forEach((btn) => {
      btn.onclick = () => { location.hash = `#/set/${btn.dataset.set}`; };
    });
  const nav = (over) => {
    const q = new URLSearchParams({ sort, rar, own, col, ...over });
    location.hash = `#/set/${r.id}?${q.toString()}`;
  };
  view().querySelector('#f-sort').onchange = (e) => nav({ sort: e.target.value });
  view().querySelector('#loose-toggle').onchange = async (e) => {
    e.target.disabled = true;
    try {
      await api.setLoose(r.id, e.target.checked);
      setDetail(r);   // re-render: counts and owned marks reflect the new mode
    } catch (err) { toast(err.message, true); e.target.disabled = false; }
  };
  view().querySelectorAll('#f-rar .chip').forEach((c) => c.onclick = () => nav({ rar: c.dataset.rar }));
  view().querySelectorAll('#f-own .chip').forEach((c) => c.onclick = () => nav({ own: c.dataset.own }));
  view().querySelectorAll('#f-col .chip').forEach((c) => c.onclick = () => nav({ col: c.dataset.col }));

  // Quick-select bulk-applies the star to the whole set, so "how do I collect
  // this set" is one click instead of a hundred. It re-renders in place, keeping
  // the current filters and scroll intent.
  view().querySelectorAll('#q-collect .qs-btn').forEach((btn) => {
    btn.onclick = async () => {
      view().querySelectorAll('.qs-btn').forEach((b) => { b.disabled = true; });
      try {
        const res = await api.bulkCollect(r.id, btn.dataset.collect);
        toast(`Coleccionando ${res.collecting} de ${cards.length}`);
        setDetail(r);
      } catch (err) {
        toast(err.message, true);
        view().querySelectorAll('.qs-btn').forEach((b) => { b.disabled = false; });
      }
    };
  });

  // The collecting toggle is a per-card exception on top of any bulk rule.
  view().querySelectorAll('[data-toggle]').forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const wasCollecting = btn.dataset.collecting === '1';
      btn.disabled = true;
      try {
        await api.setCardInSet(r.id, btn.dataset.toggle, wasCollecting ? 'drop' : 'keep');
        setDetail(r);
      } catch (err) { toast(err.message, true); btn.disabled = false; }
    };
  });
  wireCardClicks();
}

function cardCheckHtml(c) {
  const art = cardArt(c);
  return `<div class="card${c.owned ? '' : ' missing'}${c.collecting ? '' : ' not-collecting'}"
       data-card="${esc(c.card_id)}">
    <div class="art">
      ${art ? `<img src="${esc(art)}" alt="${esc(c.label)}" loading="lazy">`
            : placeholder(c.number, c.official_set_id)}
      ${c.owned ? `<span class="badge own">✓${c.quantity > 1 ? ' ×' + c.quantity : ''}</span>` : ''}
      <button class="collect-toggle${c.collecting ? ' on' : ''}"
              data-toggle="${esc(c.card_id)}" data-collecting="${c.collecting ? 1 : 0}"
              title="${c.collecting ? 'Coleccionando — clic para sacar de la lista'
                                    : 'No en la lista — clic para coleccionar'}">
        ${c.collecting ? '★' : '☆'}
      </button>
    </div>
    <div class="meta"><span class="name">${esc(c.label)}</span>
      <span class="num">#${esc(c.number)}</span></div>
  </div>`;
}

const sorter = (key) => ({
  number: (a, b) => (a.number_sort ?? 0) - (b.number_sort ?? 0),
  name: (a, b) => String(a.label).localeCompare(String(b.label)),
  rarity: (a, b) => String(a.rarity || '').localeCompare(String(b.rarity || ''))
                    || (a.number_sort ?? 0) - (b.number_sort ?? 0),
  owned: (a, b) => (b.owned ? 1 : 0) - (a.owned ? 1 : 0) || (a.number_sort ?? 0) - (b.number_sort ?? 0),
}[key] || ((a, b) => (a.number_sort ?? 0) - (b.number_sort ?? 0)));

function slotHtml(slot) {
  const art = cardArt(slot);
  // Holding a copy lifts the greyed-out treatment; reaching the target earns the
  // tick. A card you have one of but want three of is neither missing nor done.
  const complete = !!slot.complete;
  // Missing cards show their art too, dimmed and hatched by CSS, so the set
  // reads as a complete checklist. Catalog art is served from local disk, so
  // this costs no third-party requests.
  return `<div class="card${slot.owned ? '' : ' missing'}" data-card="${esc(slot.card_id)}">
    <div class="art">
      ${art
        ? `<img src="${esc(art)}" alt="${esc(slot.label)}" loading="lazy">`
        : placeholder(slot.number, slot.official_set_id)}
      ${complete ? '<span class="badge own">✓</span>' : ''}
      ${slot.owned && !complete
        ? `<span class="badge partial">${slot.quantity}/${slot.target}</span>` : ''}
      ${complete && slot.quantity > 1 ? `<span class="badge qty">×${slot.quantity}</span>` : ''}
    </div>
    <div class="label">
      <span class="nm">${esc(slot.label || '—')}</span>
      <span class="no">#${esc(slot.number || '?')}</span>
    </div>
  </div>`;
}

/* ------------------------------------------------------------ collection */
async function collection(r) {
  const f = {
    set: r.params.get('set') || '',
    condition: r.params.get('condition') || '',
    variant: r.params.get('variant') || '',
    language: r.params.get('language') || '',
    rarity: r.params.get('rarity') || '',
    q: r.params.get('q') || '',
    rating: r.params.get('rating') || '',
    rating_min: r.params.get('rating_min') || '',
    type: r.params.get('type') || '',
    edition: r.params.get('edition') || '',
    min_quantity: r.params.get('min_quantity') || '',
    sort: r.params.get('sort') || 'set',
    page_size: 240,
  };
  // Owned is the default: the inventory is what you reach for most often, and
  // All pulls every slot in the personal sets.
  const showAll = r.params.get('show_all') === '1';
  if (showAll) f.show_all = '1';
  const [res, setList] = await Promise.all([api.collection(f), api.sets()]);
  const t = res.totals;

  const sel = (id, label, options, cur) => `
    <select id="${id}"><option value="">${label}</option>${options.map((o) =>
      `<option value="${esc(o.key)}"${o.key === cur ? ' selected' : ''}>${esc(o.label)}</option>`
    ).join('')}</select>`;

  view().innerHTML = `
    <h1>Cartas</h1>
    <p class="sub">${showAll
      ? `${t.owned_slots ?? 0} / ${t.slots ?? 0} cartas conseguidas · ${
          t.physical_cards} físicas`
      : `${t.unique_cards} cartas diferentes · ${t.physical_cards} cartas físicas · ${
          res.total} registros`}</p>

    <div class="mode-toggles">
      <div class="mode-toggle">
        <span class="chip${showAll ? '' : ' on'}" data-mode="owned">En colección</span>
        <span class="chip${showAll ? ' on' : ''}" data-mode="all">Todas las del set</span>
      </div>
      <div class="mode-toggle">
        ${[['', 'Todas'], ['1', 'En Hall of Fame']]
          .map(([v, label]) => `<span class="chip${f.rating_min === v ? ' on' : ''}"
            data-qmin="${v}">${label}</span>`).join('')}
      </div>
    </div>

    <div class="toolbar">
      <input id="f-q" type="search" placeholder="Buscar…" value="${esc(f.q)}">
      ${sel('f-set', 'Todos los sets', setList.data.map((s) => ({ key: s.id, label: s.name })), f.set)}
      ${sel('f-condition', 'Condición', META.conditions, f.condition)}
      ${sel('f-variant', 'Variante', META.variants, f.variant)}
      ${sel('f-language', 'Idioma', META.languages, f.language)}
      ${sel('f-rarity', 'Rareza', META.rarities.map((x) => ({ key: x, label: x })), f.rarity)}
      ${sel('f-rating', 'Hall of Fame',
        [{ key: '0', label: 'Sin rating' }].concat(META.ratings.filter((x) => x.value > 0)
          .map((x) => ({ key: String(x.value), label: `★ ${x.value}` }))), f.rating)}
      ${sel('f-type', 'Tipo', META.types.map((t) => ({ key: t, label: t })), f.type)}
      ${sel('f-edition', 'Edición', META.editions, f.edition)}
      ${sel('f-min_quantity', 'Cantidad',
        [1, 2, 3, 4, 5].map((n) => ({ key: String(n), label: `${n} o más` })), f.min_quantity)}
      ${sel('f-sort', '', [
        { key: 'set', label: 'Por set' }, { key: 'name', label: 'Por nombre' },
        { key: 'number', label: 'Por número' }, { key: 'rarity', label: 'Por rareza' },
        { key: 'quantity', label: 'Por cantidad' }, { key: 'rating', label: 'Por Hall of Fame' },
        { key: 'recent', label: 'Más recientes' },
      ], f.sort)}
      <span class="spacer">${res.data.length} de ${res.total}</span>
    </div>

    ${res.data.length
      ? `<div class="card-grid">${res.data.map(itemHtml).join('')}</div>`
      : '<div class="empty">No hay cartas con estos filtros.</div>'}`;

  const apply = (overrides = {}) => {
    const p = new URLSearchParams();
    for (const k of ['q', 'set', 'condition', 'variant', 'language', 'rarity',
                     'rating', 'type', 'edition', 'min_quantity', 'sort']) {
      const v = view().querySelector(`#f-${k}`).value;
      if (v) p.set(k, v);
    }
    if (f.rating_min && !('rating_min' in overrides)) p.set('rating_min', f.rating_min);
    if (showAll && !('show_all' in overrides)) p.set('show_all', '1');
    for (const [k, v] of Object.entries(overrides)) {
      if (v) p.set(k, v); else p.delete(k);
    }
    location.hash = `#/cartas?${p}`;
  };
  view().querySelectorAll('[data-mode]').forEach((chip) => {
    chip.onclick = () => apply({ show_all: chip.dataset.mode === 'all' ? '1' : '' });
  });
  view().querySelectorAll('[data-qmin]').forEach((chip) => {
    chip.onclick = () => {
      // rating_min=1 is "has any rank at all", since 0 means unranked.
      // Clearing the exact-rating select avoids the two filters fighting.
      view().querySelector('#f-rating').value = '';
      apply({ rating_min: chip.dataset.qmin, rating: '' });
    };
  });
  view().querySelectorAll('.toolbar select').forEach((s) => { s.onchange = apply; });
  const q = view().querySelector('#f-q');
  q.onchange = apply;
  q.onkeydown = (e) => { if (e.key === 'Enter') apply(); };
  wireCardClicks();
}

function itemHtml(i) {
  /* Prefer the user's own photo, then the catalog image.
     In "All" mode an unowned slot has no physical copy, so it renders as the
     grey hatched placeholder rather than art the user does not have. */
  const owned = i.owned !== false;
  // display_photo is the best-conditioned copy of this card across every row,
  // so a Damaged scan never stands in for a Near Mint one you also own.
  const shown = i.display_photo || i.photos?.find((p) => p.is_primary) || i.photos?.[0];
  const src = owned ? (shown ? photoUrl(shown) : cardArt(i)) : cardArt(i);
  const v = i.value || {};
  return `<div class="card${owned ? '' : ' missing'}" data-card="${esc(i.card_id)}">
    <div class="art">
      ${src ? `<img src="${esc(src)}" alt="${esc(i.name || i.label)}" loading="lazy">`
            : placeholder(i.number, i.official_set_id)}
      ${owned && i.quantity > 1 ? `<span class="badge qty">×${i.quantity}</span>` : ''}
      ${owned && i.rating ? `<span class="badge hof-badge${i.rating < 7 ? ' fav' : ''}">★${i.rating}</span>` : ''}
      ${owned && v.total != null ? `<span class="badge val">${esc(eur(v.total))}</span>` : ''}
    </div>
    <div class="label">
      <span class="nm">${esc(i.name || i.label || '—')}</span>
      <span class="no">#${esc(i.number)}${owned && i.condition ? ` · ${esc(i.condition)}` : ''}</span>
    </div>
  </div>`;
}

/* ---------------------------------------------------------- mantenimiento */
async function mantenimiento() {
  const [job, mods] = await Promise.all([api.jobStatus(), api.modifiers()]);

  view().innerHTML = `
    <h1>Mantenimiento</h1>
    <p class="sub">Tareas que hablan con fuentes externas y tardan minutos.</p>

    <div class="stat-grid">
      <div class="stat">
        <div class="k">Actualizar precios</div>
        <div class="note">Vuelve a consultar el precio de cada impresión que tenés.
          Los precios manuales no se tocan.</div>
        <div class="btn-row"><button class="btn primary" id="do-prices">Actualizar precios ahora</button></div>
      </div>
      <div class="stat">
        <div class="k">Sincronizar lista de sets</div>
        <div class="note">Descarga el catálogo completo de sets para poder
          buscarlos al instante y sin conexión. <strong class="warn-text">⚠ Gasta
          ~12 consultas de la API</strong> — hacelo una sola vez.</div>
        <div class="btn-row"><button class="btn" id="do-sync">Sincronizar lista de sets</button></div>
      </div>
    </div>

    <h2 style="margin-top: 16px;">Objetivos por lote</h2>
    <p class="sub">Cuántas copias querés de cada carta, desde un CSV.
      Descargá el actual, editá la columna y volvé a subirlo.</p>
    <div class="stat">
      <div class="btn-row" style="flex-wrap:wrap;gap:8px;align-items:center">
        <a class="btn" id="dl-targets" download>Descargar CSV actual</a>
        <label class="btn primary" for="up-targets" style="cursor:pointer">Subir CSV</label>
        <input type="file" id="up-targets" accept=".csv,text/csv" hidden>
      </div>
      <div class="note">Columnas: <code>card_id</code>, <code>card_name</code>
        (referencia), <code>target_quantity</code>. El objetivo es de la carta, así
        que vale en todos los sets donde aparezca. No exporta los sets hidden.</div>
      <div id="targets-result"></div>
    </div>

    <h2 style="margin-top: 16px;">Revisión de datos</h2>
    <p class="sub">Busca desajustes de vocabulario — un grado renombrado, una
      rareza escrita de dos formas — que no dan error y sí dan números mal.</p>
    <div id="health-state"><div class="note">Comprobando…</div></div>
    <h2 "margin-top: 16px;">Consultas a la API</h2>
    <p class="sub">Las últimas 24 horas, moviéndose contigo — no se reinicia a
      medianoche, porque no sabemos a qué hora se reinicia la del plan.</p>
    <div id="budget-state"></div>

    <h2 style="margin-top: 16px;">Estado</h2>
    <div id="job-state" class="missing-list"></div>

    <h2 style="margin-top: 16px;">Multiplicadores de precio</h2>
    <p class="sub">El precio de una impresión se ajusta por la condición de la carta.</p>
    <div class="modifier-grid">${Object.entries(mods).map(([kind, rows]) => `
      <div class="stat">
        <div class="k">${esc(kind)}</div>
        ${Object.entries(rows).map(([key, value]) => `
          <div class="form-row" style="align-items:center;gap:8px;margin:6px 0">
            <span style="flex:1">${esc(key)}</span>
            <input type="number" step="0.05" min="0.05" value="${value}"
                   data-kind="${esc(kind)}" data-key="${esc(key)}"
                   style="width:90px">
          </div>`).join('')}
      </div>`).join('')}</div>

    <h2 style="margin-top: 16px;">Sets ocultos</h2>
    <p class="sub">Sets que ocultaste de la colección con la ✕. Siguen importados
      y no cuentan para el progreso; mostralos de nuevo acá.</p>
    <div id="hidden-sets"></div>

    <h2 style="margin-top: 16px;">DB Sets</h2>
    <p class="sub">Buscá un set y añadilo. Trae sus cartas, sus versiones y sus
      precios de una vez; después no cuesta consultas abrirlas.</p>
    <div class="field" style="max-width:420px">
      <input id="ep-search" type="search" placeholder="Neo Genesis, Fossil, BS…"
             autocomplete="off">
      <div class="note" id="ep-note">Los que ya conocés salen al instante.
        Buscar uno nuevo cuesta una consulta.</div>
    </div>
    <div id="ep-list" class="episode-grid"></div>`;

  renderJob(job);
  renderHealth();
  renderHiddenSets();
  wireEpisodes();
  renderBudgets(job.budgets);
  view().querySelector('#do-prices').onclick = () => startJob(api.refreshAsync);
  // Inline two-step confirm: the first click arms it (so the API-cost warning is
  // acknowledged), the second runs. No blocking dialog.
  const syncBtn = view().querySelector('#do-sync');
  syncBtn.onclick = async () => {
    if (syncBtn.dataset.armed !== '1') {
      syncBtn.dataset.armed = '1';
      syncBtn.classList.add('danger');
      syncBtn.textContent = 'Confirmar — gasta ~12 consultas';
      return;
    }
    syncBtn.disabled = true;
    syncBtn.textContent = 'Sincronizando…';
    try {
      const res = await api.syncCatalog();
      toast(`Catálogo sincronizado: ${res.synced} sets. Ya podés buscarlos sin gastar consultas.`);
      loadEpisodes(view().querySelector('#ep-search').value.trim());
      const st = await api.jobStatus();
      if (st && st.budgets) renderBudgets(st.budgets);
    } catch (e) {
      toast(e.message, true);
    }
    syncBtn.disabled = false;
    syncBtn.dataset.armed = '';
    syncBtn.classList.remove('danger');
    syncBtn.textContent = 'Sincronizar lista de sets';
  };
  const dl = view().querySelector('#dl-targets');
  if (dl) dl.href = api.exportTargetsUrl();

  const up = view().querySelector('#up-targets');
  if (up) {
    up.onchange = async () => {
      const file = up.files && up.files[0];
      if (!file) return;
      const box = view().querySelector('#targets-result');
      box.innerHTML = '<div class="note">Procesando…</div>';
      try {
        renderTargetImport(box, await api.importTargets(file));
      } catch (e) {
        box.innerHTML = `<div class="import-bad">${esc(e.message)}</div>`;
      }
      up.value = '';        // same file twice in a row must re-trigger
    };
  }

  view().querySelectorAll('.modifier-grid input').forEach((input) => {
    input.onchange = async () => {
      try {
        await api.setModifier(input.dataset.kind, input.dataset.key, Number(input.value));
        toast(`${input.dataset.key}: ×${input.value}`);
      } catch (e) { toast(e.message, true); }
    };
  });
  if (job.status === 'running') pollJob();
}

/* The summary leads with what changed, because "45 updated" on a file the user
   already applied would be a lie — unchanged rows are counted separately. Every
   rejected row keeps its line number so the spreadsheet is fixed in one pass. */
function renderTargetImport(box, r) {
  const changes = (r.changes || []).map((c) =>
    `<li><code>${esc(c.card_id)}</code> ${c.from} → <strong>${c.to}</strong></li>`).join('');
  const problems = (r.problems || []).map((p) =>
    `<li>línea ${p.line}${p.card_id ? ` · <code>${esc(p.card_id)}</code>` : ''} — ${esc(p.error)}</li>`).join('');

  box.innerHTML = `
    <div class="import-summary ${r.errors ? 'partial' : 'ok'}">
      <strong>${r.updated}</strong> actualizados ·
      ${r.unchanged} sin cambios ·
      <span class="${r.errors ? 'bad' : ''}">${r.errors} con problemas</span>
    </div>
    ${changes ? `<details class="import-detail"><summary>Cambios (${r.updated})</summary>
       <ul>${changes}</ul></details>` : ''}
    ${problems ? `<details class="import-detail" open><summary>Problemas (${r.errors})</summary>
       <ul class="bad">${problems}</ul></details>` : ''}`;
}

/* Silent fallbacks are the failure mode here, so the absence of an error is
   not evidence of health — it is what every one of these bugs looked like. */
async function renderHealth() {
  const box = view().querySelector('#health-state');
  if (!box) return;
  let r;
  try { r = await api.health(); } catch { box.innerHTML = ''; return; }

  if (!r.findings.length) {
    box.innerHTML = '<div class="empty">Sin desajustes. '
      + 'Grados, rarezas, números y fechas de set son consistentes.</div>';
    return;
  }
  box.innerHTML = `<ul class="health-list">${r.findings.map((f) => `
      <li class="h-${esc(f.level)}">
        <div class="h-msg">${esc(f.message)}</div>
        ${f.detail.length ? `<div class="h-detail">${
          f.detail.slice(0, 6).map(esc).join(' · ')}${
          f.detail.length > 6 ? ` … +${f.detail.length - 6}` : ''}</div>` : ''}
      </li>`).join('')}</ul>`;
}

async function renderHiddenSets() {
  const box = view().querySelector('#hidden-sets');
  if (!box) return;
  let r;
  try { r = await api.hiddenSets(); } catch { box.innerHTML = ''; return; }

  if (!r.data.length) {
    box.innerHTML = '<div class="empty">Ningún set oculto.</div>';
    return;
  }
  box.innerHTML = `<div class="hidden-list">${r.data.map((s) => `
      <div class="hidden-row">
        ${s.logo_url ? `<img src="${esc(s.logo_url)}" alt="" loading="lazy">`
                     : '<div class="noimg"></div>'}
        <span class="h-name">${esc(s.name)}</span>
        <button class="btn xs" data-show="${esc(s.id)}">Mostrar</button>
      </div>`).join('')}</div>`;
  box.querySelectorAll('[data-show]').forEach((btn) => {
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        await api.setHidden(btn.dataset.show, false);
        toast('Set visible de nuevo en la colección.');
        renderHiddenSets();
      } catch (e) { toast(e.message, true); btn.disabled = false; }
    };
  });
}

/* What is left of a metered allowance.

   Worth a permanent place rather than an error message: the number only
   matters before you press the button, and by the time a run stops halfway it
   is too late to have wanted it. */
function renderBudgets(budgets) {
  const box = view().querySelector('#budget-state');
  if (!box) return;
  if (!budgets || !budgets.length) {
    box.innerHTML = `<div class="empty">Sin fuentes con límite configuradas.</div>`;
    return;
  }
  box.innerHTML = budgets.map((b) => {
    const pct = b.limit ? Math.min(100, Math.round(100 * b.used / b.limit)) : 0;
    const level = pct >= 90 ? 'bad' : pct >= 70 ? 'warn' : 'ok';
    return `<div class="stat budget ${level}">
        <div class="k">${esc(b.provider)}</div>
        <div class="budget-num"><strong>${b.remaining}</strong> disponibles</div>
        <div class="bar"><span style="width:${pct}%"></span></div>
        <div class="note">${b.used} de ${b.limit} usadas en las últimas
          ${b.window_hours} h. Las más viejas van saliendo solas.</div>
      </div>`;
  }).join('');
}

/* Adding a set is the cheap moment to spend requests: one set answers every
   future question about its cards for nothing. The list leads with the logo
   because that is how anyone actually recognises a set. */
function episodeCard(e) {
  const added = e.imported;
  return `<div class="episode ${added ? 'added' : ''}">
      ${e.logo ? `<img src="${esc(e.logo)}" alt="" loading="lazy">`
                : '<div class="noimg"></div>'}
      <div class="e-name">${esc(e.name)}</div>
      <div class="e-meta">${esc(e.code || '')} · ${esc((e.released_at || '').slice(0, 4))}
        ${e.cards_total ? ` · ${e.cards_total} cartas` : ''}</div>
      ${added
        ? `<div class="e-added">${e.products} productos importados</div>`
        : `<button class="btn xs" data-add="${e.id}">Añadir</button>`}
    </div>`;
}

async function loadEpisodes(q) {
  const list = view().querySelector('#ep-list');
  const note = view().querySelector('#ep-note');
  if (!list) return;
  list.innerHTML = '<div class="note">Buscando…</div>';
  let r;
  try { r = await api.episodes(q); }
  catch (e) { list.innerHTML = `<div class="import-bad">${esc(e.message)}</div>`; return; }

  if (!r.episodes.length) {
    list.innerHTML = '<div class="empty">Ningún set con ese nombre.</div>';
    return;
  }

  // Ordenar del set más viejo al más nuevo
  list.innerHTML = r.episodes
    .sort((a, b) => (a.released_at || '').localeCompare(b.released_at || ''))
    .map(episodeCard)
    .join('');

  list.querySelectorAll('[data-add]').forEach((btn) => {
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = 'Importando…';
      try {
        const res = await api.importEpisode(Number(btn.dataset.add));
        toast(`${res.name}: ${res.cards} cartas, ${res.requests} consultas`);
        loadEpisodes(view().querySelector('#ep-search').value.trim());
        renderHealth();
      } catch (e) {
        toast(e.message, true);
        btn.disabled = false;
        btn.textContent = 'Añadir';
      }
    };
  });

  if (note) note.textContent = q
    ? `${r.episodes.length} resultado(s) para «${q}».`
    : 'Los que ya conocés salen al instante. Buscar uno nuevo cuesta una consulta.';
}

function wireEpisodes() {
  const input = view().querySelector('#ep-search');
  if (!input) return;
  loadEpisodes('');
  let t;
  input.oninput = () => {
    clearTimeout(t);
    t = setTimeout(() => loadEpisodes(input.value.trim()), 350);
  };
}

function renderJob(job) {
  if (job && job.budgets) renderBudgets(job.budgets);
  const box = view().querySelector('#job-state');
  if (!box) return;
  if (!job || job.status === 'idle') {
    box.innerHTML = '<div class="empty">Sin tareas ejecutadas en esta sesión.</div>';
    return;
  }
  const label = { running: 'En curso', done: 'Terminada', failed: 'Falló' }[job.status];
  box.innerHTML = `
    <div class="missing-row">
      <span class="n">${esc(job.name || '')}</span>
      <span>${esc(label)}${job.started_at ? ` · ${esc(job.started_at)}` : ''}</span>
      <span class="r">${job.error
        ? `<span style="color:var(--bad)">${esc(job.error)}</span>`
        : esc(job.result ? JSON.stringify(job.result) : '')}</span>
    </div>`;
}

async function startJob(fn) {
  try {
    renderJob(await fn());
    pollJob();
  } catch (e) { toast(e.message, true); }
}

/* Polled rather than streamed: these finish in minutes, and a socket for two
   buttons would be more moving parts than the job itself. */
function pollJob() {
  clearInterval(window.__jobPoll);
  window.__jobPoll = setInterval(async () => {
    try {
      const job = await api.jobStatus();
      renderJob(job);
      if (job.status !== 'running') {
        clearInterval(window.__jobPoll);
        toast(job.status === 'done' ? 'Tarea terminada' : `Tarea fallida: ${job.error}`,
              job.status !== 'done');
      }
    } catch { clearInterval(window.__jobPoll); }
  }, 3000);
}

/* --------------------------------------------------------------- missing */
async function missing(r) {
  const { data: setList } = await api.sets();
  const setId = r.id || r.params.get('set') || setList[0]?.id;
  const sort = r.params.get('sort') || 'number';
  if (!setId) { view().innerHTML = '<div class="empty">No hay sets.</div>'; return; }

  const [rows, s] = await Promise.all([api.missing(setId, sort), api.set(setId)]);
  const p = s.progress || {};

  view().innerHTML = `
    <h1>Cartas faltantes</h1>
    <p class="sub">${esc(s.name)} · ${
      rows.data.filter((m) => m.missing_entirely).length} de ${p.target} únicas · faltan ${
      rows.data.reduce((a, m) => a + Math.max(0, m.still_needed || 0), 0)} copias</p>

    <div class="toolbar">
      <select id="f-set">${setList.map((x) => `<option value="${esc(x.id)}"${
        x.id === setId ? ' selected' : ''}>${esc(x.name)} (${x.target - x.owned})</option>`).join('')}</select>
      <select id="f-sort">
        <option value="number"${sort === 'number' ? ' selected' : ''}>Por número</option>
        <option value="name"${sort === 'name' ? ' selected' : ''}>Por nombre</option>
        <option value="rarity"${sort === 'rarity' ? ' selected' : ''}>Por rareza</option>
      </select>
      <span class="spacer">Usa esta vista como wishlist</span>
    </div>

    ${rows.data.length ? `<div class="missing-list">${rows.data.map((m) => `
      <div class="missing-row" data-card="${esc(m.card_id)}">
        <span class="n">#${esc(m.number || '?')}</span>
        <span>${esc(m.label || '')}</span>
        ${m.missing_entirely
          ? (m.target > 1 ? `<span class="tag">faltan ${m.still_needed} copias</span>` : '')
          : `<span class="tag">tenés ${m.held} de ${m.target}</span>`}
        <span class="r">${esc(m.rarity || '')}</span>
      </div>`).join('')}</div>`
      : '<div class="empty">🎉 Set completo.</div>'}`;

  const nav = () => { location.hash = `#/missing/${view().querySelector('#f-set').value}?sort=${
    view().querySelector('#f-sort').value}`; };
  view().querySelector('#f-set').onchange = nav;
  view().querySelector('#f-sort').onchange = nav;
  wireCardClicks();
}

/* ----------------------------------------------------------------- glue */
function wireCardClicks() {
  view().querySelectorAll('[data-card]').forEach((n) => {
    n.onclick = () => { if (n.dataset.card) openCard(n.dataset.card); };
  });
}

function wireSearch() {
  const input = document.getElementById('global-search');
  const box = document.getElementById('search-results');
  let timer;
  input.oninput = () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { box.hidden = true; return; }
    timer = setTimeout(async () => {
      try {
        const res = await api.search(q);
        const owned = new Set(res.collection.map((c) => c.card_id));
        box.innerHTML = res.cards.length ? res.cards.map((c) => `
          <div class="row" data-card="${esc(c.id)}">
            <img src="${esc(cardArt(c))}" alt="" loading="lazy">
            <div><div>${esc(c.name)}</div>
              <div class="meta">${esc(c.set_name)} #${esc(c.number)}${
                owned.has(c.id) ? ' · en colección' : ''}</div></div>
          </div>`).join('') : '<div class="meta" style="padding:10px">Sin resultados</div>';
        box.hidden = false;
        box.querySelectorAll('[data-card]').forEach((n) => {
          n.onclick = () => { box.hidden = true; input.value = ''; openCard(n.dataset.card); };
        });
      } catch (e) { toast(e.message, true); }
    }, 220);
  };
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-wrap')) box.hidden = true;
  });
}

boot();
