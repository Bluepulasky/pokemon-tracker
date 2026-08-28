/* The card modal — the central interaction point (spec §28).
   Shows catalog info, every physical variant held (swipeable on mobile, §6),
   the add/edit form, photos, and the price breakdown. */

import { api } from './api.js';
import { cardArt, el, esc, eur, hofBadge, photoUrl, toast } from './ui.js';

let META = null;
let MULTIPLIERS = {};
let onChange = () => {};

export function initModal(meta, changeHandler) {
  META = meta;
  onChange = changeHandler;
  api.modifiers().then((m) => { MULTIPLIERS = m.variant || {}; }).catch(() => {});
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

/* Variants offered are the ones the chosen edition was actually printed in —
   a Base Set holo can be 1st Edition or Shadowless, a modern card cannot. */
/* Print runs live in the Edición dropdown, so they are excluded here. Offering
   "1st Edition" in both boxes asks the same question twice and leaves it unclear
   which one the saved row reflects. */
const EDITION_KEYS = ["first_edition", "shadowless"];

function variantOpts(variants, selected) {
  const allowed = ((variants && variants.length)
    ? META.variants.filter((v) => variants.includes(v.key))
    : META.variants
  ).filter((v) => !EDITION_KEYS.includes(v.key));
  return opts(allowed, selected);
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
          <div class="field card-sets">
            <label>Cuenta para</label>
            <div class="set-chips">${setChips(card)}</div>
            <div class="note">Una regla puede dejar una carta afuera —
              «sin holos» también saca a Metal Energy. Podés añadirla a mano.</div>
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

function variantCard(item) {
  const v = item.value || {};
  const label = (kind, key) => (META[kind].find((x) => x.key === key) || {}).label || key;
  return `<div class="variant-card" data-item="${item.id}" data-variant="${esc(item.variant)}">
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
  const printings = card.available_printings || [];
  const current = printings.find((p) => p.card_id === card.id) || printings[0] || {};
  return `<form class="add-form" data-card="${esc(card.id)}">
    <div class="field versions-field" style="margin-bottom:12px">
      <label>Versión en Cardmarket</label>
      <div class="version-list" data-versions-for="${esc(card.id)}">
        <div class="note">Buscando versiones…</div>
      </div>
      <div class="note">Cada opción es un producto real con su propio precio.
        La imagen y el stock son para reconocer cuál tenés.</div>
      <div class="version-picked" hidden></div>
    </div>
    ${printings.length > 1 ? `
    <div class="field" style="margin-bottom:12px">
      <label>Edición / Set actual</label>
      <select name="printing">
        ${printings.map((p) => `<option value="${p.id ?? ''}" data-card="${esc(p.card_id)}"${
          p.card_id === card.id ? ' selected' : ''}>${esc(p.display_name)}${
          p.is_reprint ? ' (reimpresión)' : ''}</option>`).join('')}
      </select>
      <div class="note">Esta carta existe en varias ediciones. Elige la que tienes.</div>
    </div>` : ''}
    <div class="legacy-fields">
    <div class="field" style="margin-bottom:12px">
      <label>Edición</label>
      <select name="edition">
        ${(card.editions && card.editions.length)
          ? card.editions.map((e) => `<option value="${esc(e)}">${esc(e)}</option>`).join('')
          : `<option value="">Unlimited</option>
             <option value="first_edition">1st Edition</option>
             <option value="shadowless">Shadowless</option>`}
      </select>
      <div class="note edition-note"></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Variante</label>
        <select name="variant">${variantOpts(current.variants)}</select></div>
    </div>
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

    <div class="field mult-box" hidden style="margin-top:12px">
      <label>Multiplicador 1st Edition</label>
      <input type="number" step="0.1" min="0.1" inputmode="decimal">
      <div class="note">Ninguna fuente cotiza la 1st Edition por separado, así que
        el sobreprecio se aplica con este factor. Editable y compartido por todas.</div>
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
  wireSetPinning(root, card, onChange);

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
  const printingSel = form.querySelector('[name=printing]');
  const editionSel = form.querySelector('[name=edition]');
  const variantSel = form.querySelector('[name=variant]');

  /* A printing's variant list comes from the catalogue, so a single option means
     there is nothing to choose — showing an active dropdown with one entry only
     invites a pointless click. */
  const refreshVariants = () => {
    const chosen = (card.available_printings || [])
      .find((p) => String(p.id ?? '') === (printingSel ? printingSel.value : ''))
      || (card.available_printings || [])[0];
    variantSel.innerHTML = variantOpts(chosen && chosen.variants);
    variantSel.disabled = variantSel.options.length <= 1;

    /* When the print runs are known from the imported products, they ARE the
       options and there is nothing to disable — the list is already only what
       exists. The rule below is for cards with no products imported, where the
       runs have to be inferred from the set instead. That inference is keyed on
       catalogue set ids, so it silently says "no 1st Edition" for any catalogue
       whose ids differ, which is what it did here. */
    const fromProducts = Array.isArray(card.editions) && card.editions.length > 0;
    if (!fromProducts) {
      const keys = (chosen && chosen.variants) || [];
      for (const opt of editionSel.options) {
        if (!opt.value) continue;
        opt.disabled = !keys.includes(opt.value);
      }
      if (editionSel.selectedOptions[0]?.disabled) editionSel.value = '';
    }
    const available = [...editionSel.options].filter((o) => !o.disabled).length;
    editionSel.disabled = available <= 1;
    form.querySelector('.edition-note').textContent = editionSel.disabled
      ? (fromProducts
          ? 'Esta carta salió en una sola tirada.'
          : 'Este set no tuvo tiradas 1st Edition ni Shadowless.')
      : '';
    updateMultiplierField();
  };

  /* The premium is shown only when it applies, because that is the moment it
     means something — and it is editable there because one figure cannot be
     right for a Charizard and a common at once. */
  function updateMultiplierField() {
    const box = form.querySelector('.mult-box');
    const active = editionSel.value === 'first_edition';
    box.hidden = !active;
    if (active) box.querySelector('input').value = MULTIPLIERS.first_edition ?? 2;
  }

  if (printingSel) printingSel.onchange = refreshVariants;
  editionSel.onchange = updateMultiplierField;
  refreshVariants();

  form.querySelector('.mult-box input').onchange = async (e) => {
    const value = Number(e.target.value) || 1;
    try {
      await api.setModifier('variant', 'first_edition', value);
      MULTIPLIERS.first_edition = value;
      toast(`Multiplicador 1st Edition: ×${value}`);
      onChange();
    } catch (err) { toast(err.message, true); }
  };

  form.querySelector('.cancel').onclick = closeModal;

  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    btn.disabled = true;
    try {
      const chosen = printingSel?.selectedOptions?.[0];
      await api.addItem({
        // Picking a different edition records that printing's catalog card, so
        // the slot is still satisfied and the physical edition is preserved.
        card_id: chosen ? chosen.dataset.card : card.id,
        printing_id: (printingSel && printingSel.value)
          ? Number(printingSel.value) : undefined,
        // A chosen edition IS the variant we store: 1st Edition and Shadowless
        // are print runs, and the collection records one variant per row.
        variant: editionSel.value || form.variant.value,
        language: form.language.value,
        condition,
        quantity: Number(form.quantity.value) || 1,
        // The version the user actually picked. Once this is set the card no
        // longer needs resolving at price time: it IS a Cardmarket product.
        market_product_id: form.dataset.productId
          ? Number(form.dataset.productId) : undefined,
      });
      toast(`${card.name} añadida`);
      onChange();
      openCard(card.id);              // reopen so the new variant shows immediately
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

    /* Typed prices exist because the feed has real gaps — every WOTC promo comes
       back with none — and because a listing in front of you beats an average.
       Clearing the box hands the printing back to the feed. */
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



    /* Every quote we hold, not one blended number.

       Two providers quoting the same market and disagreeing several times over
       means one of them has the wrong card. An average would turn that into a
       believable figure and hide it, so they are listed side by side and a
       refused quote says who else claims its product. */
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

function editVariant(vc, id, cardId) {
  const tags = vc.querySelectorAll('.tag');
  const cur = {
    variant: META.variants.find((v) => v.label === tags[0].textContent)?.key || 'normal',
    condition: tags[1].textContent.trim(),
    language: META.languages.find((l) => l.label === tags[2].textContent)?.key || 'es',
    quantity: Number(tags[3].textContent.replace('×', '')) || 1,
  };
  vc.innerHTML = `
    <div class="field"><label>Variante</label>
      <select name="variant">${opts(META.variants, cur.variant)}</select></div>
    <div class="field" style="margin-top:8px"><label>Condición</label>
      <select name="condition">${opts(META.conditions.map((c) =>
        ({ key: c.key, label: `${c.key} — ${c.label}` })), cur.condition)}</select></div>
    <div class="field" style="margin-top:8px"><label>Idioma</label>
      <select name="language">${opts(META.languages, cur.language)}</select></div>
    <div class="field" style="margin-top:8px"><label>Cantidad</label>
      <input name="quantity" type="number" min="1" value="${cur.quantity}" inputmode="numeric"></div>
    <div class="btn-row">
      <button class="btn primary save">Guardar</button>
      <button class="btn ghost cancel">Cancelar</button>
    </div>`;
  vc.querySelector('.cancel').onclick = () => openCard(cardId);
  vc.querySelector('.save').onclick = async () => {
    try {
      await api.updateItem(id, {
        variant: vc.querySelector('[name=variant]').value,
        condition: vc.querySelector('[name=condition]').value,
        language: vc.querySelector('[name=language]').value,
        quantity: Number(vc.querySelector('[name=quantity]').value) || 1,
      });
      toast('Actualizado');
      onChange();
      openCard(cardId);
    } catch (e) { toast(e.message, true); }
  };
}


/* ------------------------------------------------------------------ quotes */

/* One price, from the source that maps a version to a real Cardmarket
   product. Other stores appear only when that one has nothing to say, because
   a second opinion is noise when the first is authoritative. */

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

  if (best) {                       // the authoritative one: say where, nothing more
    box.innerHTML = `<div class="price-src">${esc(STORE[best.market])}</div>`;
    return;
  }
  if (!usable.length) { box.innerHTML = ''; return; }

  box.innerHTML = `<ul class="price-alts">${usable.map((q) =>
    `<li><span>${esc(STORE[q.market] || q.market)}</span>
         <span>${money(q.price, q.currency)}</span></li>`).join('')}</ul>`;
}


/* ---------------------------------------------------------------- versions */

/* Every product Cardmarket sells for this card, not a filtered guess at which
   one you meant. Two entries can look alike — Jungle Flareon comes back twice
   with nearly the same price and stock, and only one is a real product — so
   the image, the stock and the price are all shown and the choice is yours. */

function versionTile(v) {
  const price = v.price != null ? `${Number(v.price).toFixed(2)} €` : '—';
  const stock = v.available != null ? `${v.available} en venta` : 'sin stock';
  return `<button type="button" class="version" data-product="${v.market_product_id}">
      ${v.image ? `<img src="${esc(v.image)}" alt="" loading="lazy">` : '<div class="noimg"></div>'}
      <span class="v-code">${esc(v.code || '')}</span>
      ${v.version ? `<span class="v-name">${esc(v.version)}</span>` : ''}
      <span class="v-price">${price}</span>
      <span class="v-stock">${esc(stock)}</span>
    </button>`;
}

async function renderVersions(box, form, cardId) {
  let versions = [];
  try {
    ({ versions } = await api.versions(cardId));
  } catch (e) {
    box.innerHTML = `<div class="note">No se pudieron cargar las versiones
      (${esc(e.message)}). Usá los campos de abajo.</div>`;
    return;                     // legacy fields stay visible
  }
  if (!versions.length) {
    box.innerHTML = `<div class="note">Sin versiones conocidas para esta carta.
      Usá los campos de abajo.</div>`;
    return;                     // legacy fields stay visible
  }
  box.innerHTML = versions.map(versionTile).join('');

  /* The dropdowns stay. The picker fills them in, it does not replace them.

     Replacing them would mean trusting the version list to be complete, and it
     is not: Jungle Flareon comes back with three products where Cardmarket has
     two, and the label on JU 19 says "1st Edition" for a card Cardmarket does
     not split at all. Extra entries and wrong labels are both confirmed;
     "never omits" is not. Until it is, the person holding the card keeps the
     final say. */
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


/* What the picked version means for the rest of the form.

   Choosing a product answers questions the fields below were asking, so it
   answers them: leaving "Unlimited" selected while a Shadowless product is
   picked would record a card nobody chose. The fields stay editable — the
   version label upstream is not always right, and the person holding the card
   is a better judge than the label. */

const EDITION_FROM_VERSION = [
  [/1st\s*edition\s*shadowless/i, 'shadowless'],
  [/shadowless/i, 'shadowless'],
  [/1st\s*edition/i, 'first_edition'],
  [/unlimited/i, ''],
];

function applyVersion(form, v) {
  if (!v) return;

  const edition = form.querySelector('[name=edition]');
  const label = v.version || '';
  if (edition) {
    // The options are the real version strings now, so the picked one is
    // selectable as itself — including "1st Edition Shadowless", which the old
    // three fixed options could not express at all.
    let opt = [...edition.options].find((o) => o.value === label);
    if (!opt) {
      const match = EDITION_FROM_VERSION.find(([re]) => re.test(label));
      if (match) opt = [...edition.options].find((o) => o.value === match[1]);
    }
    if (opt) {
      opt.disabled = false;
      edition.disabled = false;
      edition.value = opt.value;
    }
  }

  // Holo or not is in the rarity, which is the one thing the label never says.
  const variant = form.querySelector('[name=variant]');
  if (variant) {
    const wanted = /holo/i.test(v.rarity || '') ? 'holo' : 'normal';
    const opt = [...variant.options].find((o) => o.value === wanted);
    if (opt) variant.value = wanted;
  }

  const summary = form.querySelector('.version-picked');
  if (summary) {
    const bits = [v.code, v.version, v.rarity].filter(Boolean).map(esc);
    summary.innerHTML = `Se guardará como <strong>${bits.join(' · ')}</strong>
      — producto Cardmarket <code>${v.market_product_id}</code>`;
    summary.hidden = false;
  }
}


/* ------------------------------------------------------------- set pinning */

/* A card excluded by a rule looks exactly like a card that does not exist,
   until you can see which sets it counts towards and why. "regla" means the
   set's own rule put it there; "a mano" means someone did, and a rebuild will
   leave it alone. */

function setChips(card) {
  const inSets = card.in_sets || [];
  if (!inSets.length) {
    return '<span class="set-chip none">No cuenta para ningún set</span>';
  }
  return inSets.map((s) => `<span class="set-chip ${s.source === 'manual' ? 'manual' : ''}">
      ${esc(s.name)}<small>${s.source === 'manual' ? 'a mano' : 'regla'}</small>
      ${s.source === 'manual'
        ? `<button class="unpin" data-set="${esc(s.id)}" title="Quitar">&times;</button>`
        : ''}
    </span>`).join('');
}

async function wireSetPinning(root, card, onChange) {
  const box = root.querySelector('.card-sets');
  if (!box) return;

  box.querySelectorAll('.unpin').forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api.unpinCard(btn.dataset.set, card.id);
        toast('Quitada del set');
        onChange();
        openCard(card.id);
      } catch (e) { toast(e.message, true); }
    };
  });

  // Offer only the sets it is not already in.
  let all = [];
  try { ({ data: all } = await api.sets()); } catch { return; }
  const already = new Set((card.in_sets || []).map((s) => s.id));
  const missing = all.filter((s) => !already.has(s.id));
  if (!missing.length) return;

  const pick = el('select', 'pin-picker');
  pick.innerHTML = '<option value="">Añadir a un set…</option>'
    + missing.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
  pick.onchange = async () => {
    if (!pick.value) return;
    try {
      await api.pinCard(pick.value, card.id);
      toast('Añadida al set');
      onChange();
      openCard(card.id);
    } catch (e) { toast(e.message, true); pick.value = ''; }
  };
  box.querySelector('.set-chips').appendChild(pick);
}
