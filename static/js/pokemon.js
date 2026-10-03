/* SPA shell: hash routing + the four views. */

import { api } from './api.js';
import { closeModal, initModal, openCard } from './modal.js';
import { cardArt, el, esc, eur, hofBadge, lineChart, pct, photoUrl, placeholder,
         progressBar, toast } from './ui.js';

const view = () => document.getElementById('view');
let META = null;
let _collGrid = null;
let _collLoaded = 0;

document.addEventListener('keydown', (e) => {
    if (!e.shiftKey) return;
    if (e.key === 'ArrowLeft') {
        document.querySelector('.set-nav-side.left .set-nav')?.click();
    }
    if (e.key === 'ArrowRight') {
        document.querySelector('.set-nav-side.right .set-nav')?.click();
    }
});

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
  const shortId = (id) => id.split('-').slice(0, 2).join('-').toUpperCase();
  const points = hist.data.map((s) => ({
    label: s.captured_on.slice(5),
    year: s.captured_on.slice(0, 4),
    value: s.value_eur,
  }));

  view().innerHTML = `
    <h1>Mi colección</h1>

    <div class="stat-grid">
      <div class="stat accent"><div class="k">Valor estimado</div>
        <div class="v">${esc(eur(v.total_eur))}</div>
        ${v.unpriced_items ? `<div class="note">${v.unpriced_items} sin precio conocido</div>` : ''}</div>
      <div class="stat"><div class="k">Cartas únicas</div><div class="v">${d.unique_cards}</div></div>
      <div class="stat"><div class="k">Cartas físicas</div><div class="v">${d.physical_cards}</div></div>
      <div class="stat"><div class="k">Pokémon únicos</div><div class="v">${d.unique_pokemon}</div></div>
      <div class="stat"><div class="k">Sets completos</div>
        <div class="v">${d.sets_complete}<small> / ${d.sets_total}</small></div>
        ${progressBar(d.sets_complete, d.sets_total)}
        </div>
      <div class="stat"><div class="k">Progreso (únicas)</div>
        <div class="v">${pct(d.completion_pct)}</div>
        ${progressBar(d.owned_cards, d.target_cards)}
        </div>
      <div class="stat"><div class="k">Progreso (copias)</div>
        <div class="v">${pct(d.copies_pct)}</div>
        ${progressBar(d.copies_held, d.copies_target)}
        </div>
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
          <span class="n">${esc(shortId(t.card_id))}</span>
          <span>${esc(t.name)}</span>
          <span class="tag2">${esc(t.variant)} ${esc(t.condition)}</span>
          <span class="r">${esc(eur(t.value))}</span>
        </div>`).join('')
      : '<div class="empty">Todavía no hay precios. Ejecuta una actualización de precios.</div>'}</div>

    <div class="btn-row">
      <button class="btn" id="refresh-prices">Actualizar precios ahora</button>
      <span class="note" style="align-self:center">
        Última actualización: ${esc(d.last_price_refresh || 'nunca')}</span>
    </div>`;
  lineChart.init();
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
    <div class="sub">${data.length} sets personalizados ·
       ${data.reduce((a, s) => a + s.owned, 0)} / ${data.reduce((a, s) => a + s.target, 0)} cartas</div>
    ${Object.entries(groups).map(([g, list]) => `
      <h2  style="margin-top: 12px;">${esc(g)}</h2>
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
  let sort = r.params.get('sort') || 'number';

  const isHolo = (c) => /holo/i.test(c.rarity || '');
  const cards = (s.cards || []).map((c) => ({
    card_id: c.id, label: c.name, name: c.name, number: c.number,
    number_sort: c.number_sort, rarity: c.rarity,
    image_small_url: c.image_small_url, image_local: c.image_local,
    official_set_id: c.official_set_id,
    owned: (c.owned_qty || 0) > 0, quantity: c.owned_qty || 0,
    collecting: !!c.collecting, holo: isHolo(c),
    supertype: c.supertype || null,
    types: JSON.parse(c.types_json || '[]'),
    rating: c.rating || 0,
  }));

  const collecting = cards.filter((c) => c.collecting).length;
  const rarities = [...new Set(cards.map(c => c.rarity).filter(Boolean))].sort();

  const filters = {
    q: '',
    rar: new Set(rarities),
    owned: true, missing: true,
    collecting: true, notCollecting: false,
    hof: new Set(['0', ...META.ratings.filter(x => x.value > 0).map(x => String(x.value))]),
    types: new Set(META.types),
    colors: new Set(META.energy_types || []),
  };

  function applyFilters() {
    let shown = cards;
    if (filters.q) {
      const q = filters.q.toLowerCase();
      shown = shown.filter(c =>
        c.name.toLowerCase().includes(q) || c.number.toLowerCase().includes(q));
    }
    if (filters.rar.size < rarities.length)
      shown = shown.filter(c => filters.rar.has(c.rarity));
    if (!filters.owned || !filters.missing)
      shown = shown.filter(c => (filters.owned && c.owned) || (filters.missing && !c.owned));
    if (!filters.collecting || !filters.notCollecting)
      shown = shown.filter(c =>
        (filters.collecting && c.collecting) || (filters.notCollecting && !c.collecting));
    if (filters.hof.size < META.ratings.length + 1)
      shown = shown.filter(c => filters.hof.has(String(c.rating || 0)));
    if (filters.types.size < META.types.length)
      shown = shown.filter(c => filters.types.has(c.supertype));
    if (filters.colors.size < (META.energy_types || []).length)
      shown = shown.filter(c =>
        c.types.length === 0 || c.types.some(t => filters.colors.has(t)));
    shown = [...shown].sort(sorter(sort));
    view().querySelector('.card-grid').innerHTML = shown.map(cardCheckHtml).join('');
    wireCardClicks();
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
    const shownOwned = shown.filter(c => c.owned).length;
    view().querySelector('#toolbar-count').textContent = `${shownOwned} / ${shown.length}`;
  }

  view().innerHTML = `
    <div class="set-nav-row">
      <div class="set-nav-side left">
        ${prev ? `<button class="set-nav" data-set="${prev.id}">
          <span class="nav-arrow">‹‹</span>
          <span class="nav-name">${esc(prev.name)}</span>
        </button>` : ''}
      </div>
      <div class="set-nav-center">
        <h1>${esc(s.name)}</h1>
      </div>
      <div class="set-nav-side right">
        ${next ? `<button class="set-nav" data-set="${next.id}">
          <span class="nav-name">${esc(next.name)}</span>
          <span class="nav-arrow">››</span>
        </button>` : ''}
      </div>
    </div>
    ${progressBar(p.owned, collecting)}

    <div class="loose-toggle">
      <label>
        <input type="checkbox" id="loose-toggle" ${s.loose_completion ? 'checked' : ''}>
        <span>Cualquier versión cuenta para el progreso</span>
      </label>
    </div>

    <div class="toolbar" id="toolbar">
      <div class="sub" id="toolbar-count">${p.owned} / ${collecting}</div>
      <button class="toolbar-toggle" id="toolbar-toggle" title="Filtros">🔍</button>
      <div class="toolbar-filters" id="toolbar-filters">
        <div class="toolbar-filters-inner">

          <div class="filter-section">
            <input type="search" id="f-q" placeholder="Buscar por nombre o número…">
          </div>

          <div class="filter-section">
            <div class="filter-label">Rareza</div>
            <div class="chips" id="f-rar">
              ${rarities.map(rr => `<span class="chip on" data-rar="${esc(rr)}">${esc(rr)}</span>`).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Colección</div>
            <div class="filter-row">
              <div class="chips" id="f-own">
                <span class="chip on" data-own="owned">Poseídas</span>
                <span class="chip on" data-own="missing">Faltantes</span>
              </div>
              <div class="chips" id="f-col">
                <span class="chip on" data-col="collecting">Coleccionando</span>
                <span class="chip" data-col="notCollecting">No coleccionando</span>
              </div>
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Hall of Fame
              <button class="chip-toggle-all" data-group="hof">✕ todo</button>
            </div>
            <div class="chips" id="f-hof">
              <span class="chip on" data-hof="0">Sin rating</span>
              ${META.ratings.filter(x => x.value > 0).map(x =>
                `<span class="chip on" data-hof="${x.value}">${x.value}★</span>`
              ).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Supertipo</div>
            <div class="chips" id="f-type">
              ${META.types.map(t =>
                `<span class="chip on" data-type="${esc(t)}">${esc(t)}</span>`
              ).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Color
              <button class="chip-toggle-all" data-group="color">✕ todo</button>
            </div>
            <div class="chips" id="f-color">
              ${(META.energy_types || []).map(t =>
                `<span class="chip on" data-color="${esc(t)}">${esc(t)}</span>`
              ).join('')}
            </div>
          </div>

        </div>
      </div>
    </div>

    <div class="sort-select">
        <button type="button" id="sort-button">
            <span id="sort-label">Por número</span>
            <span class="sort-arrow">▴</span>
        </button>

        <div class="sort-options" id="sort-options">
            <div class="sort-option ${sort === 'number' ? 'selected' : ''}" data-value="number">Por número</div>
            <div class="sort-option ${sort === 'name' ? 'selected' : ''}" data-value="name">Por nombre</div>
            <div class="sort-option ${sort === 'rarity' ? 'selected' : ''}" data-value="rarity">Por rareza</div>
            <div class="sort-option ${sort === 'still_needed' ? 'selected' : ''}" data-value="still_needed">Por pendientes</div>
        </div>
    </div>

    <div class="card-grid">${cards.filter(c => c.collecting).sort(sorter(sort)).map(cardCheckHtml).join('')}</div>`;

    const sortSelect = view().querySelector('.sort-select');
    const sortButton = view().querySelector('#sort-button');
    const sortOptions = view().querySelector('#sort-options');
    const sortLabel = view().querySelector('#sort-label');

    sortLabel.textContent = {
      number: 'Por número',
      name: 'Por nombre',
      rarity: 'Por rareza',
      still_needed: 'Por pendientes'
    }[sort] || 'Por número';

    sortSelect.onclick = (e) => e.stopPropagation();

    sortButton.onclick = () => {
      sortSelect.classList.toggle('open');
    };

    sortOptions.onclick = (e) => {
        const option = e.target.closest('.sort-option');
        if (!option) return;

        sort = option.dataset.value;

        sortOptions.querySelectorAll('.sort-option').forEach(o => {
            o.classList.toggle('selected', o === option);
        });

        sortLabel.textContent = option.textContent;
        sortSelect.classList.remove('open');

        applyFilters();
    };

  view().querySelectorAll('.set-nav').forEach((btn) => {
    btn.onclick = () => { location.hash = `#/set/${btn.dataset.set}`; };
  });

  view().querySelector('#loose-toggle').onchange = async (e) => {
    e.target.disabled = true;
    try {
      await api.setLoose(r.id, e.target.checked);
      setDetail(r);
    } catch (err) { toast(err.message, true); e.target.disabled = false; }
  };

  view().querySelector('#toolbar-toggle').onclick = () => {
    const panel = view().querySelector('#toolbar-filters');
    const toggle = view().querySelector('#toolbar-toggle');
    const open = panel.classList.toggle('open');
    toggle.classList.toggle('active', open);
  };

  view().querySelectorAll('#f-rar .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.rar.add(c.dataset.rar);
      else filters.rar.delete(c.dataset.rar);
      applyFilters();
    };
  });

  view().querySelectorAll('#f-own .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.dataset.own === 'owned') filters.owned = c.classList.contains('on');
      if (c.dataset.own === 'missing') filters.missing = c.classList.contains('on');
      applyFilters();
    };
  });

  view().querySelectorAll('#f-col .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.dataset.col === 'collecting') filters.collecting = c.classList.contains('on');
      if (c.dataset.col === 'notCollecting') filters.notCollecting = c.classList.contains('on');
      applyFilters();
    };
  });

  let searchTimer;
  view().querySelector('#f-q').oninput = (e) => {
    filters.q = e.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilters, 250);
  };

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

  view().querySelectorAll('#f-hof .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.hof.add(c.dataset.hof);
      else filters.hof.delete(c.dataset.hof);
      applyFilters();
    };
  });

  view().querySelectorAll('#f-type .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.types.add(c.dataset.type);
      else filters.types.delete(c.dataset.type);
      applyFilters();
    };
  });

  view().querySelectorAll('#f-color .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.colors.add(c.dataset.color);
      else filters.colors.delete(c.dataset.color);
      applyFilters();
    };
  });
  
  view().querySelectorAll('.chip-toggle-all').forEach(btn => {
    btn.onclick = () => {
      const group = btn.dataset.group;
      const chips = view().querySelectorAll(`#f-${group} .chip`);
      const allOn = [...chips].every(c => c.classList.contains('on'));
      chips.forEach(c => {
        if (allOn) c.classList.remove('on');
        else c.classList.add('on');
      });
      // sync filter state
      if (group === 'hof') {
        if (allOn) filters.hof.clear();
        else filters.hof = new Set(['0', ...META.ratings.filter(x => x.value > 0).map(x => String(x.value))]);
      }
      if (group === 'color') {
        if (allOn) filters.colors.clear();
        else filters.colors = new Set(META.energy_types || []);
      }
      btn.textContent = allOn ? '✓ todo' : '✕ todo';
      applyFilters();
    };
  });

  applyFilters();
  wireCardClicks();
}

function cardCheckHtml(c) {
  const art = cardArt(c);
  return `<div class="card${c.owned ? '' : ' missing'}${c.collecting ? '' : ' not-collecting'}"
     data-card="${esc(c.card_id)}" data-number="${esc(c.number)}" data-name="${esc(c.label)}">
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
  const page = Number(r.params.get('page') || 1);
  const isAppend = page > 1 && _collGrid;

  const SET_CODES = {
    'bs-completo':  'BS',  'ju-completo':  'JU',  'wp-completo':  'WP',
    'fo-completo':  'FO',  'tr-completo':  'TR',  'gh-completo':  'GH',
    'gc-completo':  'GC',  'ng-completo':  'NG',  'nd-completo':  'ND',
    '161-completo': 'SI',  'nr-completo':  'NR',  'nde-completo': 'NDE',
    'trr-completo': 'TRR',
  };

  const SET_IDS = {
    'bs-completo': 'bs',
    'ju-completo': 'ju',
    'wp-completo': 'wp',
    'fo-completo': 'fo',
    'tr-completo': 'tr',
    'gh-completo': 'b2',
    'gc-completo': 'gc',
    'ng-completo': 'lc',
    'nd-completo': 'sw',
    '161-completo': 'blw',
    'nr-completo': 'evo',
    'nde-completo': 'cel',
    'trr-completo': 'crz',
  };

  const f = {
    sort: r.params.get('sort') || 'set',
    page_size: 150,
    page,
  };
  const showAll = r.params.get('show_all') === '1';
  if (showAll) f.show_all = '1';
  const uniqueReprints = showAll && r.params.get('unique_reprints') === '1';
  if (uniqueReprints) f.unique_reprints = '1';

  const [res, setList] = await Promise.all([api.collection(f), api.sets()]);
  const t = res.totals;

  if (isAppend) {
    _collGrid.insertAdjacentHTML('beforeend', res.data.map(itemHtml).join(''));
    _collLoaded += res.data.length;
    const wrap = view().querySelector('#load-more-wrap');
    if (_collLoaded >= res.total) {
      wrap?.remove();
    } else {
      wrap.querySelector('#load-more').textContent =
        `Mostrando ${_collLoaded} de ${res.total} - Cargar más`;
    }
    wireCardClicks();
    return;
  }

  _collGrid = null;
  _collLoaded = res.data.length;

  // Filter state — all on by default
  const allSets = setList.data.map(s => String(s.id));
  const allConditions = META.conditions.map(c => c.key);
  const allLanguages = META.languages.map(l => l.key);

  const filters = {
    q: '',
    sets: new Set(allSets),
    conditions: new Set(allConditions),
    languages: new Set(allLanguages),
    showAll,
    uniqueReprints,
    rar: new Set(META.rarities),
    hof: new Set(['0', ...META.ratings.filter(x => x.value > 0).map(x => String(x.value))]),
    types: new Set(META.types),
    colors: new Set(META.energy_types || []),
    sort: f.sort,
  };

  let sort = f.sort;
  let allData = res.data;

  function applyFilters() {
    let shown = allData;

    if (filters.q) {
      const q = filters.q.toLowerCase();
      shown = shown.filter(c =>
        (c.name || '').toLowerCase().includes(q) ||
        (c.number || '').toLowerCase().includes(q));
    }
    console.log('SET IDS:', allSets);
    console.log('CARD SET IDS:', [...new Set(allData.map(c => c.official_set_id))]);
    if (filters.sets.size < allSets.length)
      shown = shown.filter(c =>
        filters.sets.has(
          Object.keys(SET_IDS).find(key => SET_IDS[key] === c.official_set_id)
        )
      );
    if (filters.conditions.size < allConditions.length)
      shown = shown.filter(c => filters.conditions.has(c.condition));
    if (filters.languages.size < allLanguages.length)
      shown = shown.filter(c => filters.languages.has(c.language));
    if (filters.rar.size < META.rarities.length)
      shown = shown.filter(c => filters.rar.has(c.rarity));
    if (filters.hof.size < META.ratings.length + 1)
      shown = shown.filter(c => filters.hof.has(String(c.rating || 0)));
    if (filters.types.size < META.types.length)
      shown = shown.filter(c => filters.types.has(c.supertype));
    if (filters.colors.size < (META.energy_types || []).length)
      shown = shown.filter(c =>
        !c.types?.length || c.types.some(t => filters.colors.has(t)));

    const physicalCards = shown.reduce((sum, c) => sum + (c.quantity || 0), 0);

    view().querySelector('#toolbar-count').textContent = showAll
      ? `${shown.length} cartas diferentes · ${physicalCards} físicas`
      : `${shown.length} cartas diferentes · ${physicalCards} físicas · ${shown.length} registros`;

    view().querySelector('.card-grid').innerHTML = shown.map(itemHtml).join('');
    wireCardClicks();
  }

  view().innerHTML = `
    <h1>Cartas</h1>

    <div class="toolbar" id="toolbar">
      <div class="sub" id="toolbar-count">${showAll
      ? `${t.owned_slots ?? 0} / ${t.slots ?? 0} cartas conseguidas · ${t.physical_cards} físicas`
      : `${t.unique_cards} cartas diferentes · ${t.physical_cards} cartas físicas · ${t.item_rows} registros`}</div>
      <button class="toolbar-toggle" id="toolbar-toggle" title="Filtros">🔍</button>
      <div class="toolbar-filters" id="toolbar-filters">
        <div class="toolbar-filters-inner">

          <div class="filter-section">
            <input type="search" id="f-q" placeholder="Buscar por nombre o número…">
          </div>

          <div class="filter-section">
            <div class="filter-label">Set
              <button class="chip-toggle-all" data-group="set">✕ todo</button>
            </div>
            <div class="chips" id="f-set">
              ${setList.data.map(s =>
                `<span class="chip on" data-set="${s.id}">${SET_CODES[s.id] || s.id}</span>`
              ).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Vista</div>
            <div class="filter-row">
              <div class="chips">
                <span class="chip${showAll ? '' : ' on'}" data-mode="owned">En colección</span>
                <span class="chip${showAll ? ' on' : ''}" data-mode="all">Todas las del set</span>
              </div>
              ${showAll ? `<div class="chips">
                <span class="chip${!uniqueReprints ? ' on' : ''}" data-uniq="">Todas las versiones</span>
                <span class="chip${uniqueReprints ? ' on' : ''}" data-uniq="1">Reprints únicos</span>
              </div>` : ''}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Rareza
              <button class="chip-toggle-all" data-group="rar">✕ todo</button>
            </div>
            <div class="chips" id="f-rar">
              ${META.rarities.map(rr =>
                `<span class="chip on" data-rar="${esc(rr)}">${esc(rr)}</span>`
              ).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Condición
              <button class="chip-toggle-all" data-group="cond">✕ todo</button>
            </div>
            <div class="chips" id="f-cond">
              ${META.conditions.map(c =>
                `<span class="chip on" data-cond="${esc(c.key)}">${esc(c.label)}</span>`
              ).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Idioma
              <button class="chip-toggle-all" data-group="lang">✕ todo</button>
            </div>
            <div class="chips" id="f-lang">
              ${META.languages.map(l =>
                `<span class="chip on" data-lang="${esc(l.key)}">${esc(l.label)}</span>`
              ).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Hall of Fame
              <button class="chip-toggle-all" data-group="hof">✕ todo</button>
            </div>
            <div class="chips" id="f-hof">
              <span class="chip on" data-hof="0">Sin rating</span>
              ${META.ratings.filter(x => x.value > 0).map(x =>
                `<span class="chip on" data-hof="${x.value}">${x.value}★</span>`
              ).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Supertipo</div>
            <div class="chips" id="f-type">
              ${META.types.map(t =>
                `<span class="chip on" data-type="${esc(t)}">${esc(t)}</span>`
              ).join('')}
            </div>
          </div>

          <div class="filter-section">
            <div class="filter-label">Color
              <button class="chip-toggle-all" data-group="color">✕ todo</button>
            </div>
            <div class="chips" id="f-color">
              ${(META.energy_types || []).map(t =>
                `<span class="chip on" data-color="${esc(t)}">${esc(t)}</span>`
              ).join('')}
            </div>
          </div>

        </div>
      </div>
    </div>

    <div class="sort-select">
      <button type="button" id="sort-button">
        <span id="sort-label">${{
          set: 'Por set', name: 'Por nombre', number: 'Por número',
          rarity: 'Por rareza', quantity: 'Por cantidad',
          rating: 'Por Hall of Fame', recent: 'Más recientes'
        }[sort] || 'Por set'}</span>
        <span class="sort-arrow">▴</span>
      </button>
      <div class="sort-options" id="sort-options">
        ${[
          ['set','Por set'],['name','Por nombre'],['number','Por número'],
          ['rarity','Por rareza'],['quantity','Por cantidad'],
          ['rating','Por Hall of Fame'],['recent','Más recientes'],
        ].map(([v, l]) =>
          `<div class="sort-option${sort === v ? ' selected' : ''}" data-value="${v}">${l}</div>`
        ).join('')}
      </div>
    </div>

    <div class="card-grid collection-grid">${res.data.map(itemHtml).join('')}</div>
    ${res.total > res.data.length ? `<div id="load-more-wrap">
      <button id="load-more">Mostrando ${res.data.length} de ${res.total} - Cargar más</button>
    </div>` : ''}`;

  _collGrid = view().querySelector('.collection-grid');

  // sort
  const sortSelectEl = view().querySelector('.sort-select');
  const sortButton = view().querySelector('#sort-button');
  const sortOptions = view().querySelector('#sort-options');
  const sortLabel = view().querySelector('#sort-label');
  sortSelectEl.onclick = (e) => e.stopPropagation();
  sortButton.onclick = () => sortSelectEl.classList.toggle('open');
  sortOptions.onclick = (e) => {
    const option = e.target.closest('.sort-option');
    if (!option) return;

    sort = option.dataset.value;

    sortOptions.querySelectorAll('.sort-option').forEach(o =>
      o.classList.toggle('selected', o === option));

    sortLabel.textContent = option.textContent;
    sortSelectEl.classList.remove('open');

    applyFilters();
  };

  // toolbar toggle
  view().querySelector('#toolbar-toggle').onclick = () => {
    const panel = view().querySelector('#toolbar-filters');
    const toggle = view().querySelector('#toolbar-toggle');
    const open = panel.classList.toggle('open');
    toggle.classList.toggle('active', open);
  };

  // mode toggles (these still need reload — they change what the API returns)
  view().querySelectorAll('[data-mode]').forEach(chip => {
    chip.onclick = () => {
      const p = new URLSearchParams();
      p.set('show_all', chip.dataset.mode === 'all' ? '1' : '');
      location.hash = `#/cartas?${p}`;
    };
  });
  view().querySelectorAll('[data-uniq]').forEach(chip => {
    chip.onclick = () => {
      const p = new URLSearchParams(location.hash.split('?')[1] || '');
      p.set('unique_reprints', chip.dataset.uniq);
      location.hash = `#/cartas?${p}`;
    };
  });
  view().querySelectorAll('[data-qmin]').forEach(chip => {
    chip.onclick = () => {
      const p = new URLSearchParams(location.hash.split('?')[1] || '');
      p.set('rating_min', chip.dataset.qmin);
      location.hash = `#/cartas?${p}`;
    };
  });

  // chip filters
  view().querySelectorAll('#f-set .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.sets.add(c.dataset.set);
      else filters.sets.delete(c.dataset.set);
      applyFilters();
    };
  });
  view().querySelectorAll('#f-rar .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.rar.add(c.dataset.rar);
      else filters.rar.delete(c.dataset.rar);
      applyFilters();
    };
  });
  view().querySelectorAll('#f-cond .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.conditions.add(c.dataset.cond);
      else filters.conditions.delete(c.dataset.cond);
      applyFilters();
    };
  });
  view().querySelectorAll('#f-lang .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.languages.add(c.dataset.lang);
      else filters.languages.delete(c.dataset.lang);
      applyFilters();
    };
  });
  view().querySelectorAll('#f-hof .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.hof.add(c.dataset.hof);
      else filters.hof.delete(c.dataset.hof);
      applyFilters();
    };
  });
  view().querySelectorAll('#f-type .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.types.add(c.dataset.type);
      else filters.types.delete(c.dataset.type);
      applyFilters();
    };
  });
  view().querySelectorAll('#f-color .chip').forEach(c => {
    c.onclick = () => {
      c.classList.toggle('on');
      if (c.classList.contains('on')) filters.colors.add(c.dataset.color);
      else filters.colors.delete(c.dataset.color);
      applyFilters();
    };
  });

  // search
  let searchTimer;
  view().querySelector('#f-q').oninput = (e) => {
    filters.q = e.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilters, 250);
  };

  // toggle-all buttons
  const toggleAllDefs = {
    set:   { filterKey: 'sets',       allFn: () => new Set(allSets) },
    rar:   { filterKey: 'rar',        allFn: () => new Set(META.rarities) },
    cond:  { filterKey: 'conditions', allFn: () => new Set(allConditions) },
    lang:  { filterKey: 'languages',  allFn: () => new Set(allLanguages) },
    hof:   { filterKey: 'hof',        allFn: () => new Set(['0', ...META.ratings.filter(x => x.value > 0).map(x => String(x.value))]) },
    color: { filterKey: 'colors',     allFn: () => new Set(META.energy_types || []) },
  };
  view().querySelectorAll('.chip-toggle-all').forEach(btn => {
    const group = btn.dataset.group;
    btn.onclick = () => {
      const chips = view().querySelectorAll(`#f-${group} .chip`);
      const allOn = [...chips].every(c => c.classList.contains('on'));
      chips.forEach(c => allOn ? c.classList.remove('on') : c.classList.add('on'));
      const def = toggleAllDefs[group];
      if (def) filters[def.filterKey] = allOn ? new Set() : def.allFn();
      btn.textContent = allOn ? '✓ todo' : '✕ todo';
      applyFilters();
    };
  });

  // load more
  const loadMoreBtn = view().querySelector('#load-more');
  if (loadMoreBtn) {
    loadMoreBtn.onclick = () => {
      const p = new URLSearchParams(location.hash.split('?')[1] || '');
      p.set('page', page + 1);
      collection({ params: p });
    };
  }

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
  // One tile per card, so the badge and the price count every copy behind it —
  // including copies that are a reprint in another set (#78). A partial price
  // is a floor, not the tile's value, and says so rather than passing for one.
  const qty = i.group_quantity ?? i.quantity;
  // The Hall of Fame rank is a judgement about the card, so it shows on a card
  // you have not got yet — the same reason the rank filter matches those (#76).
  // Hiding it meant the ranked Base Set Blastoise looked unranked next to the
  // reprint you own, which is the split all over again.
  const grouped = (i.group_card_ids?.length ?? 0) > 1;
  const price = v.total != null ? `${v.partial ? '≥' : ''}${eur(v.total)}` : '';
  const shortId = (id) => id.split('-').slice(0, 2).join('-').toUpperCase();
  return `<div class="card${owned ? '' : ' missing'}" data-card="${esc(i.card_id)}"
     data-name="${esc(i.name || i.label || '')}" data-number="${esc(i.number || '')}"
     ${grouped ? 'data-reprints="1"' : ''}>
    <div class="art">
      ${src ? `<img src="${esc(src)}" alt="${esc(i.name || i.label)}" loading="lazy">`
            : placeholder(i.number, i.official_set_id)}
      ${owned && qty > 1 ? `<span class="badge qty">×${qty}</span>` : ''}
      ${i.reprint_owned ? `<span class="badge reprint-own"
        title="No tenés esta impresión, pero sí otra versión de la carta">otra versión</span>` : ''}
      ${i.rating ? `<span class="badge hof-badge${i.rating < 7 ? ' fav' : ''}">★${i.rating}</span>` : ''}
      ${owned && price ? `<span class="badge val"${v.partial
        ? ' title="Alguna copia no tiene precio: el total es un mínimo."' : ''
        }>${esc(price)}</span>` : ''}
    </div>
    <div class="label">
      <span class="nm">${esc(i.name || i.label || '—')}</span>
      <span class="no">${esc(shortId(i.card_id))}${owned && i.condition ? ` - ${esc(i.condition)}` : ''}</span>
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

    <h2 style="margin-top: 16px;">Correcciones de datos</h2>
    <p class="sub">Corrige datos de las cartas — ilustrador y tipo
      (Pokémon/Trainer/Energy) — que quedaron vacíos en importaciones viejas,
      sin volver a importar ni gastar consultas. Se cruza por <code>card_id</code>.</p>
    <div class="stat">
      <div class="btn-row" style="flex-wrap:wrap;gap:8px;align-items:center">
        <button class="btn primary" id="apply-meta">Aplicar correcciones incluidas</button>
        <a class="btn" id="dl-meta" download>Descargar CSV actual</a>
        <label class="btn" for="up-meta" style="cursor:pointer">Subir CSV propio</label>
        <input type="file" id="up-meta" accept=".csv,text/csv" hidden>
      </div>
      <label style="display:flex;gap:6px;align-items:center;margin-top:10px">
        <input type="checkbox" id="meta-overwrite">
        <span>Sobrescribir valores existentes
          <span class="note" style="display:inline">(por defecto solo rellena los vacíos)</span></span>
      </label>
      <div class="note" style="margin-top:8px">«Aplicar correcciones incluidas» usa el
        archivo que viene con la app; «Subir CSV propio» aplica el tuyo al instante.
        Columnas: <code>card_id</code> + <code>artist</code>, <code>supertype</code>
        (Pokémon / Trainer / Energy), <code>types</code> (el color: Fire, Water…;
        dos tipos separados por <code>|</code>). Celda vacía = no toca ese campo.
        Ambas acciones respetan la casilla de arriba. El color solo llega por acá:
        tcggo no lo trae, así que un set recién importado no tiene color hasta
        aplicar el archivo.</div>
      <div id="meta-result"></div>
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

  const dlMeta = view().querySelector('#dl-meta');
  if (dlMeta) dlMeta.href = api.cardMetaExportUrl();

  const overwriteOn = () => !!view().querySelector('#meta-overwrite')?.checked;
  const applyMeta = view().querySelector('#apply-meta');
  if (applyMeta) {
    applyMeta.onclick = async () => {
      const box = view().querySelector('#meta-result');
      box.innerHTML = '<div class="note">Aplicando…</div>';
      try {
        renderMetaResult(box, await api.applyCardMeta(overwriteOn()));
      } catch (e) { box.innerHTML = `<div class="import-bad">${esc(e.message)}</div>`; }
    };
  }
  const upMeta = view().querySelector('#up-meta');
  if (upMeta) {
    upMeta.onchange = async () => {
      const file = upMeta.files && upMeta.files[0];
      if (!file) return;
      const box = view().querySelector('#meta-result');
      box.innerHTML = '<div class="note">Procesando…</div>';
      try {
        renderMetaResult(box, await api.importCardMeta(file, overwriteOn()));
      } catch (e) { box.innerHTML = `<div class="import-bad">${esc(e.message)}</div>`; }
      upMeta.value = '';
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

/* A fix run fills blanks only, so the headline is how many gaps it closed, per
   field. Unknown ids (cards this install does not have) are surfaced, not
   swallowed, so a file aimed at the wrong catalog is obvious. */
function renderMetaResult(box, r) {
  const changed = r.changed || {};
  const total = Object.values(changed).reduce((a, n) => a + n, 0);
  const parts = Object.entries(changed)
    .map(([f, n]) => `<strong>${n}</strong> ${esc(f)}`).join(' · ');
  const verb = r.overwrite ? 'Sobrescrito' : 'Rellenado';
  const headline = total ? `${verb}: ${parts}`
    : (r.overwrite ? 'Nada que cambiar (los valores ya coincidían)'
                   : 'Nada que rellenar (no había campos vacíos)');
  const unknownList = (r.unknown_ids || []).map((id) => `<code>${esc(id)}</code>`).join(', ');
  box.innerHTML = `
    <div class="import-summary ${r.unknown ? 'partial' : 'ok'}">
      ${headline}
      ${r.unknown ? ` · <span class="bad">${r.unknown} id(s) desconocidos</span>` : ''}
    </div>
    ${r.unknown ? `<details class="import-detail"><summary>Ids no encontrados en tu catálogo (${r.unknown})</summary>
       <div class="note">${unknownList}${r.unknown > 50 ? ' …' : ''}</div></details>` : ''}`;
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
  // Still listed, so searching for it does not look broken — just not offered,
  // because importing it would spend a request and fetch nothing (#75).
  const empty = e.empty && !added;
  return `<div class="episode ${added ? 'added' : ''}${empty ? ' empty' : ''}">
      ${e.logo ? `<img src="${esc(e.logo)}" alt="" loading="lazy">`
                : '<div class="noimg"></div>'}
      <div class="e-name">${esc(e.name)}</div>
      <div class="e-meta">${esc(e.code || '')} · ${esc((e.released_at || '').slice(0, 4))}
        ${e.cards_total ? ` · ${e.cards_total} cartas` : ''}</div>
      ${added
        ? `<div class="e-added">${e.products} productos importados</div>
           <button class="btn xs ghost" data-reimport="${e.id}"
             title="Vuelve a traer el set — corrige datos y precios sin re-elegir cartas">Reimportar</button>`
        : empty
          ? `<div class="e-empty">tcggo no tiene cartas para este set.
               Si existen, están dentro de otro.</div>`
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

  // Re-import an already-imported set: same endpoint, so it refreshes prices and
  // re-derives cards (splitting any that a collision had merged). Reads the cache
  // first, so it usually costs nothing — the toast reports what it spent.
  list.querySelectorAll('[data-reimport]').forEach((btn) => {
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = 'Reimportando…';
      try {
        const res = await api.importEpisode(Number(btn.dataset.reimport));
        toast(`${res.name}: ${res.cards} cartas, ${res.requests} consultas`);
        loadEpisodes(view().querySelector('#ep-search').value.trim());
        renderHealth();
      } catch (e) {
        toast(e.message, true);
        btn.disabled = false;
        btn.textContent = 'Reimportar';
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
  const onlyNoted = r.params.get('note') === '1';
  if (!setId) { view().innerHTML = '<div class="empty">No hay sets.</div>'; return; }
  const shortId = (id) => id.split('-').slice(0, 2).join('-').toUpperCase();
  const [rows, s] = await Promise.all([api.missing(setId, sort), api.set(setId)]);
  const p = s.progress || {};
  const shown = onlyNoted ? rows.data.filter((m) => m.note) : rows.data;

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
        <option value="still_needed"${sort === 'still_needed' ? ' selected' : ''}>Por pendientes</option>
      </select>
      <div class="chips seg" id="f-note">
        ${[['', 'Todas'], ['1', 'Con nota']]
          .map(([k, l]) => `<span class="chip${(onlyNoted ? '1' : '') === k ? ' on' : ''}" data-note="${k}">${l}</span>`).join('')}
      </div>
    </div>

    ${shown.length ? `<div class="missing-list">${shown.map((m) => `
      <div class="missing-row" data-card="${esc(m.card_id)}">
        <span class="n">${esc(shortId(m.card_id))}</span>
        <span class="m">x${m.still_needed}</span>
        <span class="missing-name">${esc(m.label || '')}</span>
        ${m.note ? `<small class="tag2">${esc(m.note)}</small>` : ''}</span>
        <span class="r">${esc(m.rarity || '')}</span>
      </div>`).join('')}</div>`
      : `<div class="empty">${onlyNoted ? 'Ninguna faltante con nota.' : '🎉 Set completo.'}</div>`}`;

  const nav = (note = onlyNoted ? '1' : '') => {
    const q = new URLSearchParams({ sort: view().querySelector('#f-sort').value });
    if (note) q.set('note', '1');
    location.hash = `#/missing/${view().querySelector('#f-set').value}?${q}`;
  };
  view().querySelector('#f-set').onchange = () => nav();
  view().querySelector('#f-sort').onchange = () => nav();
  view().querySelectorAll('#f-note .chip').forEach((c) => { c.onclick = () => nav(c.dataset.note); });
  wireCardClicks();
}

/* ----------------------------------------------------------------- glue */
function wireCardClicks() {
  const tiles = [...view().querySelectorAll('[data-card]')];
  const navList = tiles.map((n) => ({
    id: n.dataset.card,
    name: n.dataset.name || '',
    number: n.dataset.number || '',
  }));

  tiles.forEach((n, idx) => {
    n.onclick = () => {
      if (n.dataset.card) openCard(n.dataset.card, {
        reprints: !!n.dataset.reprints,
        navList,
        navIdx: idx,
      });
    };
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
