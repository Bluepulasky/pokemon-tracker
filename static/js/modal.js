/* The card modal — the central interaction point.
   Shows catalog info, every physical variant held (swipeable on mobile, §6),
   the add/edit form, photos, and the price breakdown. */

import { api } from './api.js';
import { cardArt, el, esc, eur, hofBadge, photoUrl, toast } from './ui.js';

let META = null;
let COND_MULTIPLIERS = {};
let onChange = () => {};

export function initModal(meta, changeHandler) {
  META = meta;
  onChange = changeHandler;
  api.modifiers().then((m) => { COND_MULTIPLIERS = m.condition || {}; }).catch(() => {});
  document.getElementById('modal-root').addEventListener('click', (e) => {
    if (e.target.id === 'modal-root') closeModal();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
}

export function closeModal() {
  const root = document.getElementById('modal-root');
  root.hidden = true;
  root.innerHTML = '';
}

const opts = (list, sel) => list
  .map((o) => `<option value="${esc(o.key)}"${o.key === sel ? ' selected' : ''}>${esc(o.label)}</option>`)
  .join('');

export async function openCard(cardId) {
  const root = document.getElementById('modal-root');
  root.hidden = false;
  root.innerHTML = '<div class="modal"><div class="loading">Cargando…</div></div>';

  let card, items;
  try {
    [card, items] = await Promise.all([api.card(cardId), api.byCard(cardId)]);
  } catch (e) { toast(e.message, true); closeModal(); return; }
  items = items.data;

  root.innerHTML = '';
  root.appendChild(el(`
    <div class="modal">
      <div class="modal-head">
        <div class="art"><img src="${esc(cardArt(card))}" alt="${esc(card.name)}" loading="lazy"></div>
        <div>
          <h3>${esc(card.name)}</h3>
          <div class="meta">${esc(card.set_name)} #${esc(card.number)}${card.rarity ? ' · ' + esc(card.rarity) : ''}</div>
          <div class="meta">${esc(card.artist || '')}</div>
          <div class="meta" style="margin-top:8px">
            ${items.length
              ? `<span class="tag" style="color:var(--good)">En colección · ${items.reduce((a, i) => a + i.quantity, 0)} física(s)</span>`
              : '<span class="tag">No poseída</span>'}
          </div>
          ${card.market_url ? `<a class="mkm" href="${esc(card.market_url)}"
             target="_blank" rel="noopener noreferrer">Ver en Cardmarket ↗</a>` : ''}
          <div class="field card-rank">
            <label>Hall of Fame</label>
            ${rankRow(card.rating || 0)}
          </div>
          <div class="field card-target">
            <label>Objetivo de copias</label>
            <input type="number" min="1" inputmode="numeric"
                   value="${Number(card.target) || 1}">
            <div class="note">La carta cuenta como conseguida al llegar a este número.</div>
          </div>
        </div>
        <button class="close" aria-label="Cerrar">&times;</button>
      </div>
      <div class="modal-body">
        ${items.length ? `<h2>Variantes en colección</h2>
          <div class="variants">${items.map(variantCard).join('')}</div>
          <div class="hr"></div>` : ''}
        <h2>${items.length ? 'Añadir otra' : 'Registrar carta'}</h2>
        ${addForm(card)}
      </div>
    </div>`));

  root.querySelector('.close').onclick = closeModal;
  wireCardRank(root, card);
  wireCardTarget(root, card);
  wireForm(root, card);
  wireVariants(root, cardId);
}

// CAMBIO 1: añadir data-first-ed, data-price-unit-base, data-price-qty,
// data-price-basis al div raíz — los lee editVariant para el preview.
function variantCard(item) {
  const v = item.value || {};
  const label = (kind, key) => (META[kind].find((x) => x.key === key) || {}).label || key;
  // Precio base sin el multiplicador de primera edición, para que el preview
  // pueda recalcular limpio en ambas direcciones.
  const condMult = v.condition_multiplier || 1;
  const priceRaw = v.unit != null
    ? (v.unit / condMult / (item.first_edition ? 2 : 1)).toFixed(4)
    : '';
  return `<div class="variant-card" data-item="${item.id}" data-variant="${esc(item.variant)}"
     data-first-ed="${item.first_edition ? '1' : '0'}"
     data-price-raw="${priceRaw}"
     data-price-qty="${item.quantity}"
     data-price-basis="${esc(v.basis || '')}">
    <div class="tags">
      <span class="tag">${esc(label('variants', item.variant))}</span>
      <span class="tag">${esc(item.condition)}</span>
      <span class="tag">${esc(label('languages', item.language))}</span>
      <span class="tag">×${item.quantity}</span>
      ${item.printing_name ? `<span class="tag ed">${esc(item.printing_name)}</span>` : ''}
    </div>
    <div class="photos${item.photos.length ? '' : ' empty'}">
      ${item.photos.length
        ? item.photos.map((p) => `<img src="${esc(photoUrl(p, false))}" data-photo="${p.id}"
             class="${p.is_primary ? 'primary' : ''}"
             title="${p.is_primary ? 'Principal' : 'Marcar como principal'}" loading="lazy">`).join('')
        : `<div class="photo-empty">
             <span>Sin fotografía</span>
             <small>Toca «Foto» para añadir una</small>
           </div>`}
    </div>
    <div class="price">${esc(eur(v.total))}
      <small>${v.basis === 'no_data' ? 'sin datos para esta impresión'
                : v.basis === 'printing_level' ? `${eur(v.unit)} × ${item.quantity} · precio de la impresión`
                : `${eur(v.unit)} × ${item.quantity}`}</small></div>
    ${item.market_url ? `<a class="mkm sm" href="${esc(item.market_url)}"
       target="_blank" rel="noopener noreferrer">Cardmarket ↗</a>` : ''}
    <div class="quotes" data-quotes-for="${esc(item.card_id)}"
         data-variant="${esc(item.variant || '')}"></div>
    <div class="field manual-price">
      <label>Precio manual</label>
      <input type="number" step="0.01" min="0" placeholder="usar el del feed"
             value="${item.value?.manual ? item.value.unit : ''}">
      <div class="note">${item.value?.manual
        ? 'Fijado a mano; el refresco no lo toca.'
        : 'Vacío = precio de la fuente.'}</div>
    </div>
    <div class="btn-row compact">
      <button class="btn xs act-photo">Foto</button>
      <button class="btn xs act-edit">Editar</button>
      <button class="btn xs danger act-del">Borrar</button>
    </div>
    <input type="file" accept="image/*" hidden class="photo-input">
  </div>`;
}

/* 0-8 as a row of targets. A slider is fiddly on a phone and hides the value,
   and this is the one control the feature exists for. */
function rankRow(current) {
  return `<div class="rank-row">
    ${META.ratings.map((r) => `<span class="rank${r.value === 0 ? ' zero' : ''}${
      Number(current) === r.value ? ' on' : ''}" data-rank="${r.value}"
      title="${esc(r.label)}">${r.value === 0 ? '—' : r.value}</span>`).join('')}
  </div>`;
}

function addForm(card) {
  return `<form class="add-form" data-card="${esc(card.id)}">
    <div class="field versions-field" style="margin-bottom:12px">
      <label>Versión en Cardmarket</label>
      <div class="version-list" data-versions-for="${esc(card.id)}">
        <div class="note">Buscando versiones…</div>
      </div>
      <div class="note">Elegí el producto que tenés — su edición y variante salen
        de ahí. La imagen, el stock y el precio son para reconocer cuál es.</div>
      <div class="version-picked" hidden></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Idioma</label>
        <select name="language">${opts(META.languages, 'es')}</select></div>
      <div class="field" style="flex:0 0 90px"><label>Cantidad</label>
        <input name="quantity" type="number" min="1" value="1" inputmode="numeric"></div>
    </div>
    <div class="field"><label>Condición</label>
      <div class="chips">${META.conditions.map((c, i) =>
        `<span class="chip${i === 0 ? ' on' : ''}" data-cond="${esc(c.key)}"
           title="${esc(c.label)}">${esc(c.key)}</span>`).join('')}</div>
    </div>
    <div class="btn-row">
      <button type="submit" class="btn primary">Guardar</button>
      <button type="button" class="btn ghost cancel">Cancelar</button>
    </div>
    <div class="note">La foto se añade después de guardar, desde la variante.</div>
  </form>`;
}

/* The rank belongs to the card, so there is one picker for the whole modal.
   It saves on click: ranking is the thing you do repeatedly while going through
   a binder, and a two-step edit would be wrong for it. */
function wireCardRank(root, card) {
  const box = root.querySelector('.card-rank');
  if (!box) return;
  box.querySelectorAll('.rank').forEach((r) => {
    r.onclick = async () => {
      const value = Number(r.dataset.rank);
      box.querySelectorAll('.rank').forEach((x) => x.classList.remove('on'));
      r.classList.add('on');
      try {
        await api.rateCard(card.id, value);
        onChange();
      } catch (e) { toast(e.message, true); }
    };
  });
}

/* The target belongs to the card, like the rank. Saved on blur rather than on
   every keystroke, since it is a number you type rather than a value you pick. */
function wireCardTarget(root, card) {
  const input = root.querySelector('.card-target input');
  if (!input) return;
  input.onchange = async () => {
    const value = Math.max(1, Number(input.value) || 1);
    input.value = value;
    try {
      await api.setTarget(card.id, value);
      onChange();
    } catch (e) { toast(e.message, true); }
  };
}

function wireForm(root, card) {
  const form = root.querySelector('.add-form');
  const versionBox = root.querySelector('.version-list');
  if (versionBox) renderVersions(versionBox, form, versionBox.dataset.versionsFor);

  let condition = META.conditions[0].key;

  form.querySelectorAll('.chip').forEach((chip) => {
    chip.onclick = () => {
      form.querySelectorAll('.chip').forEach((c) => c.classList.remove('on'));
      chip.classList.add('on');
      condition = chip.dataset.cond;
    };
  });

  form.querySelector('.cancel').onclick = closeModal;

  form.onsubmit = async (e) => {
    e.preventDefault();
    if (!form.dataset.productId) {
      toast('Elegí una versión de Cardmarket', true);
      return;
    }
    const btn = form.querySelector('button[type=submit]');
    btn.disabled = true;
    try {
      const targetCard = form.dataset.cardId || card.id;
      await api.addItem({
        card_id: targetCard,
        language: form.language.value,
        condition,
        quantity: Number(form.quantity.value) || 1,
        market_product_id: Number(form.dataset.productId),
      });
      toast(`${card.name} añadida`);
      onChange();
      openCard(targetCard);
    } catch (err) {
      toast(err.message, true);
      btn.disabled = false;
    }
  };
}

function wireVariants(root, cardId) {
  root.querySelectorAll('.variant-card').forEach((vc) => {
    const id = Number(vc.dataset.item);
    const fileInput = vc.querySelector('.photo-input');

    vc.querySelector('.act-photo').onclick = () => fileInput.click();
    fileInput.onchange = async () => {
      if (!fileInput.files[0]) return;
      toast('Subiendo foto…');
      try {
        await api.uploadPhoto(id, fileInput.files[0]);
        toast('Foto subida');
        onChange();
        openCard(cardId);
      } catch (e) { toast(e.message, true); }
    };

    vc.querySelector('.act-del').onclick = async () => {
      if (!confirm('¿Eliminar este registro de la colección?')) return;
      try {
        await api.deleteItem(id);
        toast('Registro eliminado');
        onChange();
        openCard(cardId);
      } catch (e) { toast(e.message, true); }
    };

    vc.querySelector('.act-edit').onclick = () => editVariant(vc, id, cardId);

    const manual = vc.querySelector('.manual-price input');
    if (manual) {
      manual.onchange = async () => {
        const raw = manual.value.trim();
        try {
          await api.setManualPrice(cardId, vc.dataset.variant, raw === '' ? null : Number(raw));
          toast(raw === '' ? 'Precio manual quitado' : `Precio fijado en ${raw}`);
          onChange();
          openCard(cardId);
        } catch (e) { toast(e.message, true); }
      };
    }

    const qbox = vc.querySelector('.quotes');
    if (qbox) renderQuotes(qbox, cardId, vc.dataset.variant);

    vc.querySelectorAll('[data-photo]').forEach((img) => {
      img.onclick = async () => {
        try { await api.setPrimary(Number(img.dataset.photo)); toast('Foto principal actualizada');
              onChange(); openCard(cardId); }
        catch (e) { toast(e.message, true); }
      };
    });
  });
}

// CAMBIO 2: editVariant — reemplaza el select de variante por ¿Primera edición?
// y añade un preview de precio en tiempo real.
function editVariant(vc, id, cardId) {
  // Leer precio base y metadatos del DOM (puestos por variantCard arriba).
  const priceRaw  = parseFloat(vc.dataset.priceRaw);
  const qty       = Number(vc.dataset.priceQty);
  const basis     = vc.dataset.priceBasis || '';
  const firstEdOn = vc.dataset.firstEd === '1';

  const tags = vc.querySelectorAll('.tag');
  const cur = {
    condition: tags[1].textContent.trim(),
    language:  META.languages.find((l) => l.label === tags[2].textContent)?.key || 'es',
    quantity:  Number(tags[3].textContent.replace('×', '')) || 1,
  };

  vc.innerHTML = `
    <div class="field"><label>¿Primera edición?</label>
      <select name="first_edition">
        <option value="0"${!firstEdOn ? ' selected' : ''}>No</option>
        <option value="1"${firstEdOn  ? ' selected' : ''}>Sí (×2)</option>
      </select></div>
    <div class="field" style="margin-top:8px"><label>Condición</label>
      <select name="condition">${opts(META.conditions.map((c) =>
        ({ key: c.key, label: `${c.key} — ${c.label}` })), cur.condition)}</select></div>
    <div class="field" style="margin-top:8px"><label>Idioma</label>
      <select name="language">${opts(META.languages, cur.language)}</select></div>
    <div class="field" style="margin-top:8px"><label>Cantidad</label>
      <input name="quantity" type="number" min="1" value="${cur.quantity}" inputmode="numeric"></div>
    <div class="price-preview"></div>
    <div class="btn-row">
      <button class="btn primary save">Guardar</button>
      <button class="btn ghost cancel">Cancelar</button>
    </div>`;

  // Preview en tiempo real — solo si tenemos datos de precio.
  const sel     = vc.querySelector('[name=first_edition]');
  const preview = vc.querySelector('.price-preview');

  function updatePreview() {
    if (!preview || !Number.isFinite(priceRaw)) return;
    const factor   = sel.value === '1' ? 2.0 : 1.0;
    const condKey  = vc.querySelector('[name=condition]').value;
    const condMult = COND_MULTIPLIERS[condKey] ?? 1.0;
    const newUnit  = priceRaw * condMult * factor;
    const newTotal = newUnit * qty;
    const suffix   = factor > 1 ? ' · ×2 1ª ed.' : '';
    const small    = basis === 'no_data'
      ? 'sin datos para esta impresión'
      : basis === 'printing_level'
        ? `${eur(newUnit)} × ${qty} · precio de la impresión${suffix}`
        : `${eur(newUnit)} × ${qty}${suffix}`;
    preview.innerHTML = `<div class="price">${esc(eur(newTotal))}<small>${small}</small></div>`;
  }

  sel.onchange = updatePreview;
  vc.querySelector('[name=condition]').onchange = updatePreview;
  updatePreview();   // render inmediato al abrir el formulario

  vc.querySelector('.cancel').onclick = () => openCard(cardId);

  // CAMBIO 3: save manda first_edition en lugar de variant.
  vc.querySelector('.save').onclick = async () => {
    try {
      await api.updateItem(id, {
        first_edition: vc.querySelector('[name=first_edition]').value === '1',
        condition:     vc.querySelector('[name=condition]').value,
        language:      vc.querySelector('[name=language]').value,
        quantity:      Number(vc.querySelector('[name=quantity]').value) || 1,
      });
      toast('Actualizado');
      onChange();
      openCard(cardId);
    } catch (e) { toast(e.message, true); }
  };
}


/* ------------------------------------------------------------------ quotes */

const STORE = { cardmarket: 'Cardmarket', tcgplayer: 'TCGplayer' };
const PREFERRED = 'tcggo';

function money(value, currency) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return currency === 'USD' ? `$${n.toFixed(2)}` : `${n.toFixed(2)} €`;
}

async function renderQuotes(box, cardId, variant) {
  let quotes = [];
  try {
    ({ quotes } = await api.quotes(cardId, variant));
  } catch { return; }

  const usable = quotes.filter((q) => q.trusted && q.price != null);
  const best = usable.find((q) => q.provider === PREFERRED && q.market === 'cardmarket');

  if (best) {
    box.innerHTML = `<div class="price-src">${esc(STORE[best.market])}</div>`;
    return;
  }
  if (!usable.length) { box.innerHTML = ''; return; }

  box.innerHTML = `<ul class="price-alts">${usable.map((q) =>
    `<li><span>${esc(STORE[q.market] || q.market)}</span>
         <span>${money(q.price, q.currency)}</span></li>`).join('')}</ul>`;
}


/* ---------------------------------------------------------------- versions */

function versionTile(v) {
  const price = v.price != null ? `${Number(v.price).toFixed(2)} €` : '—';
  return `<button type="button" class="version${v.is_current ? '' : ' reprint'}"
      data-product="${v.market_product_id}" data-card="${esc(v.card_id || '')}">
      ${v.image ? `<img src="${esc(v.image)}" alt="" loading="lazy">` : '<div class="noimg"></div>'}
      ${v.set ? `<span class="v-set">${esc(v.set)}</span>` : ''}
      <span class="v-code">${esc(v.code || '')}</span>
      <span class="v-price">${price}</span>
    </button>`;
}

async function renderVersions(box, form, cardId) {
  let versions = [];
  try {
    ({ versions } = await api.versions(cardId));
  } catch (e) {
    box.innerHTML = `<div class="note">No se pudieron cargar las versiones
      (${esc(e.message)}). Volvé a intentar.</div>`;
    return;
  }
  if (!versions.length) {
    box.innerHTML = `<div class="note">Sin versiones conocidas para esta carta.
      Importá su set desde Mantenimiento para poder registrarla.</div>`;
    return;
  }
  const own = versions.filter((v) => v.is_current);
  const reprints = versions.filter((v) => !v.is_current);
  box.innerHTML =
    (own.length ? own.map(versionTile).join('') : '')
    + reprints.map(versionTile).join('');

  const byId = new Map(versions.map((v) => [String(v.market_product_id), v]));
  box.querySelectorAll('.version').forEach((btn) => {
    btn.onclick = () => {
      box.querySelectorAll('.version').forEach((b) => b.classList.remove('picked'));
      btn.classList.add('picked');
      form.dataset.productId = btn.dataset.product;
      applyVersion(form, byId.get(btn.dataset.product));
    };
  });
}

function applyVersion(form, v) {
  if (!v) return;

  if (v.card_id) {
    form.dataset.cardId = v.card_id;
  } else {
    delete form.dataset.cardId;
  }

  const summary = form.querySelector('.version-picked');
  if (summary) {
    const bits = [v.code, v.set, v.version, v.rarity].filter(Boolean).map(esc);
    const note = v.is_current === false
      ? `<div class="note">Reimpresión — se guarda en <strong>${esc(v.set)}</strong>,
         no en el set que abriste.</div>` : '';
    summary.innerHTML = `Se guardará como <strong>${bits.join(' · ')}</strong>
      — producto Cardmarket <code>${v.market_product_id}</code>${note}`;
    summary.hidden = false;
  }
}