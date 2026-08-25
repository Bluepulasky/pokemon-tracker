/* The card modal — the central interaction point (spec §28).
   Shows catalog info, every physical variant held (swipeable on mobile, §6),
   the add/edit form, photos, and the price breakdown. */

import { api } from './api.js';
import { cardArt, el, esc, eur, hofBadge, photoUrl, toast } from './ui.js';

let META = null;
let onChange = () => {};

export function initModal(meta, changeHandler) {
  META = meta;
  onChange = changeHandler;
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
  wireForm(root, card);
  wireVariants(root, cardId);
}

function variantCard(item) {
  const v = item.value || {};
  const label = (kind, key) => (META[kind].find((x) => x.key === key) || {}).label || key;
  return `<div class="variant-card" data-item="${item.id}">
    <div class="tags">
      <span class="tag">${esc(label('variants', item.variant))}</span>
      <span class="tag">${esc(item.condition)}</span>
      <span class="tag">${esc(label('languages', item.language))}</span>
      <span class="tag">×${item.quantity}</span>
      ${item.printing_name ? `<span class="tag ed">${esc(item.printing_name)}</span>` : ''}
      ${hofBadge(item.rating, { compact: true })}
    </div>
    <div class="field" style="margin-bottom:8px">
      <label>Hall of Fame</label>
      ${rankRow(item.rating || 0)}
      <div class="rank-label">${esc(RATING_LABEL(item.rating || 0))}</div>
    </div>
    <div class="photos">
      ${item.photos.length
        ? item.photos.map((p) => `<img src="${esc(photoUrl(p))}" data-photo="${p.id}"
             title="${p.is_primary ? 'Principal' : 'Marcar como principal'}" loading="lazy">`).join('')
        : '<span class="note">Sin fotografía propia</span>'}
    </div>
    <div class="price">${esc(eur(v.total))}
      <small>${v.basis === 'unpriced' ? 'sin precio'
                : v.basis === 'variant_fallback' ? 'aprox.'
                : `${eur(v.unit)} × ${item.quantity}`}</small></div>
    ${item.market_url ? `<a class="mkm sm" href="${esc(item.market_url)}"
       target="_blank" rel="noopener noreferrer">Cardmarket ↗</a>` : ''}
    <div class="btn-row">
      <button class="btn ghost act-photo">Foto</button>
      <button class="btn ghost act-edit">Editar</button>
      <button class="btn ghost danger act-del">Borrar</button>
    </div>
    <input type="file" accept="image/*" capture="environment" hidden class="photo-input">
  </div>`;
}

const RATING_LABEL = (r) =>
  (META.ratings.find((x) => x.value === Number(r)) || {}).label || '';

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
  return `<form class="add-form" data-card="${esc(card.id)}">
    ${printings.length > 1 ? `
    <div class="field" style="margin-bottom:12px">
      <label>Edición / Set actual</label>
      <select name="printing">
        ${printings.map((p) => `<option value="${p.id}" data-card="${esc(p.card_id)}"${
          p.card_id === card.id ? ' selected' : ''}>${esc(p.display_name)}${
          p.is_reprint ? ' (reimpresión)' : ''}</option>`).join('')}
      </select>
      <div class="note">Esta carta existe en varias ediciones. Elige la que tienes.</div>
    </div>` : ''}
    <div class="form-row">
      <div class="field"><label>Variante</label>
        <select name="variant">${opts(META.variants)}</select></div>
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
    <div class="field" style="margin-top:12px"><label>Hall of Fame</label>
      ${rankRow(0)}
      <div class="rank-label"></div>
    </div>
    <div class="btn-row">
      <button type="submit" class="btn primary">Guardar</button>
      <button type="button" class="btn ghost cancel">Cancelar</button>
    </div>
    <div class="note">La foto se añade después de guardar, desde la variante.</div>
  </form>`;
}

function wireForm(root, card) {
  const form = root.querySelector('.add-form');
  let condition = META.conditions[0].key;
  let rating = 0;

  form.querySelectorAll('.rank').forEach((r) => {
    r.onclick = () => {
      form.querySelectorAll('.rank').forEach((x) => x.classList.remove('on'));
      r.classList.add('on');
      rating = Number(r.dataset.rank);
      form.querySelector('.rank-label').textContent = RATING_LABEL(rating);
    };
  });

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
    const btn = form.querySelector('button[type=submit]');
    btn.disabled = true;
    try {
      const printingSel = form.querySelector('[name=printing]');
      const chosen = printingSel?.selectedOptions?.[0];
      await api.addItem({
        // Picking a different edition records that printing's catalog card, so
        // the slot is still satisfied and the physical edition is preserved.
        card_id: chosen ? chosen.dataset.card : card.id,
        printing_id: printingSel ? Number(printingSel.value) : undefined,
        variant: form.variant.value,
        language: form.language.value,
        condition,
        rating,
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

    // Ranking saves on click. It is the one thing you do repeatedly while
    // going through a binder, so making it a two-step edit would be wrong.
    vc.querySelectorAll('.rank').forEach((r) => {
      r.onclick = async () => {
        const value = Number(r.dataset.rank);
        vc.querySelectorAll('.rank').forEach((x) => x.classList.remove('on'));
        r.classList.add('on');
        vc.querySelector('.rank-label').textContent = RATING_LABEL(value);
        try {
          await api.rate(id, value);
          const b = vc.querySelector('.hof');
          if (b) b.outerHTML = hofBadge(value, { compact: true }) || '<span class="hof" hidden></span>';
          onChange();
        } catch (e) { toast(e.message, true); }
      };
    });

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
