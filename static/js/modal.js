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
    <div class="field" style="margin-bottom:12px">
      <label>Edición</label>
      <select name="edition">
        <option value="">Unlimited</option>
        <option value="first_edition">1st Edition</option>
        <option value="shadowless">Shadowless</option>
      </select>
      <div class="note edition-note"></div>
    </div>
    <div class="form-row">
      <div class="field"><label>Variante</label>
        <select name="variant">${variantOpts(current.variants)}</select></div>
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
  const form = root.querySelector('.add-form');
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

    /* 1st Edition and Shadowless only exist for the early WOTC print runs. The
       catalogue knows which, so the options are disabled rather than hidden —
       the absence is itself information. */
    const keys = (chosen && chosen.variants) || [];
    for (const opt of editionSel.options) {
      if (!opt.value) continue;
      opt.disabled = !keys.includes(opt.value);
    }
    if (editionSel.selectedOptions[0]?.disabled) editionSel.value = '';
    const available = [...editionSel.options].filter((o) => !o.disabled).length;
    editionSel.disabled = available <= 1;
    form.querySelector('.edition-note').textContent = editionSel.disabled
      ? 'Este set no tuvo tiradas 1st Edition ni Shadowless.'
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

const MARKET_LABEL = { cardmarket: 'Cardmarket', tcgplayer: 'TCGplayer' };
const PROVIDER_LABEL = { tcgdex: 'TCGdex', pokemontcgio: 'pokemontcg.io' };

function money(value, currency) {
  if (value === null || value === undefined) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return currency === 'USD' ? `$${n.toFixed(2)}` : `${n.toFixed(2)} €`;
}

function quoteRow(q) {
  const range = [q.price_low, q.price_mid ?? q.price_trend, q.price_high]
    .some((v) => v !== null && v !== undefined)
    ? `<small class="range">bajo ${money(q.price_low, q.currency)}
         · medio ${money(q.price_mid ?? q.price_trend, q.currency)}
         · alto ${money(q.price_high, q.currency)}</small>`
    : '';
  const printing = q.printing ? `<span class="printing">${esc(q.printing)}</span>` : '';
  const refused = !q.trusted
    ? `<div class="refused" title="${esc(q.distrust_reason || '')}">
         no se usa — ${esc(q.distrust_reason || 'fuente poco fiable')}</div>`
    : '';
  return `<li class="${q.trusted ? '' : 'untrusted'}">
      <div class="head">
        <span class="market">${esc(MARKET_LABEL[q.market] || q.market)}</span>
        <span class="provider">${esc(PROVIDER_LABEL[q.provider] || q.provider)}</span>
        ${printing}
        <span class="amount">${money(q.price, q.currency)}</span>
      </div>
      ${range}${refused}
    </li>`;
}

async function renderQuotes(box, cardId, variant) {
  let quotes = [];
  try {
    ({ quotes } = await api.quotes(cardId, variant));
  } catch {
    return;                       // the panel is extra context, never the point
  }
  if (!quotes.length) {
    box.innerHTML = '<div class="quotes-empty">Sin cotizaciones guardadas todavía.</div>';
    return;
  }
  const eur = quotes.filter((q) => q.currency !== 'USD');
  const usd = quotes.filter((q) => q.currency === 'USD');
  box.innerHTML = `
    <details class="quotes-panel" ${quotes.some((q) => !q.trusted) ? 'open' : ''}>
      <summary>Cotizaciones (${quotes.length})</summary>
      ${eur.length ? `<ul class="quote-list">${eur.map(quoteRow).join('')}</ul>` : ''}
      ${usd.length ? `<div class="quotes-note">Otro mercado, otra moneda —
           referencia, no entra en el total.</div>
         <ul class="quote-list">${usd.map(quoteRow).join('')}</ul>` : ''}
    </details>`;
}
