/* Modal de carta — mobile.
   Una columna: pills de solo lectura arriba, la carta con swipe en el centro y
   un panel inferior (se arrastra hacia arriba) con el alta de copias. */
import { api } from './api.js';
import { cardArt, esc, eur, photoUrl, toast } from './ui.js';
import { ctx, closeModal, lockScroll, onClose, nextToken, isStale } from './modal-core.js';

const SWIPE_FRAC = 0.22;   // fracción del ancho para confirmar el cambio de carta
const FLICK_V = 0.5;       // px/ms: un gesto rápido confirma aunque sea corto
const OPEN_FRAC = 0.88;    // alto del panel abierto, fracción de la ventana
const GAP = 32;            // px de separación entre cartas al deslizar

const opts = (list, sel) => list
  .map((o) => `<option value="${esc(o.key)}"${o.key === sel ? ' selected' : ''}>${esc(o.label)}</option>`)
  .join('');

export async function openCardMobile(cardId, openOpts = {}) {
  const token = nextToken();
  const { META } = ctx;
  const root = document.getElementById('modal-root');

  const hasList = Array.isArray(openOpts.navList) && openOpts.navList.length && openOpts.navIdx >= 0;
  const list = hasList ? [...openOpts.navList] : [{ id: cardId }];
  let idx = hasList ? openOpts.navIdx : 0;

  let card = null, items = [];
  let seq = 0, busy = false;
  let scan = null, flipped = false, flipBusy = false;   // reverso: foto escaneada
  let picked = null, pendingPhoto = null;
  let condition = META.conditions[0].key;

  root.classList.add('is-mobile');
  root.hidden = false;
  lockScroll(true);
  document.querySelector('.sort-select')?.style.setProperty('display', 'none');

  root.innerHTML = `
  <div class="mm">
    <header class="mm-top">
      <button type="button" class="mm-pill mm-copies" aria-expanded="false">
        <b>–</b> copias <span class="mm-caret">▾</span>
      </button>
      <span class="mm-pill mm-goal" title="Objetivo de copias">Obj <b>–</b></span>
      <span class="mm-pill mm-hof" title="Hall of Fame">★ <b>–</b></span>
      <div class="mm-popover" hidden></div>
    </header>

    <main class="mm-stage">
      <div class="mm-track">
        <img class="mm-slide prev" alt="" draggable="false" hidden>
        <img class="mm-slide cur" alt="" draggable="false" hidden>
        <img class="mm-slide next" alt="" draggable="false" hidden>
      </div>
      <span class="mm-face-tag" hidden></span>
    </main>

    <section class="mm-sheet" data-state="peek">
      <div class="mm-handle" role="button" aria-label="Añadir copia">
        <span class="mm-grip"></span>
        <span class="mm-handle-label">Añadir copia</span>
      </div>
      <div class="mm-sheet-body">
        <div class="mm-versions"><div class="mm-note">Buscando versiones…</div></div>

        <div class="mm-field">
          <label>Idioma</label>
          <select name="language">${opts(META.languages, 'en')}</select>
        </div>
        <div class="mm-field">
          <label>Cantidad</label>
          <div class="mm-qty">
            <button type="button" data-d="-1" aria-label="Menos">−</button>
            <input name="quantity" type="number" min="1" value="1" inputmode="numeric">
            <button type="button" data-d="1" aria-label="Más">+</button>
          </div>
        </div>
        <div class="mm-field">
          <label>Condición</label>
          <div class="mm-chips">${META.conditions.map((c, i) =>
            `<button type="button" class="mm-chip${i === 0 ? ' on' : ''}" data-cond="${esc(c.key)}"
               title="${esc(c.label)}">${esc(c.key)}</button>`).join('')}</div>
        </div>
        <div class="mm-actions">
          <button type="button" class="mm-btn primary mm-save">Guardar</button>
          <input type="file" accept="image/*" class="mm-photo-input" hidden>
          <button type="button" class="mm-btn mm-photo">Foto</button>
          <button type="button" class="mm-btn mm-cancel">Cancelar</button>
        </div>
      </div>
    </section>

    <button type="button" class="mm-close" aria-label="Cerrar">&times;</button>
  </div>`;

  const $ = (s) => root.querySelector(s);
  const $$ = (s) => root.querySelectorAll(s);
  const mm = $('.mm'), stage = $('.mm-stage'), track = $('.mm-track');
  const sheet = $('.mm-sheet'), pop = $('.mm-popover'), copiesBtn = $('.mm-copies');
  mm.style.setProperty('--mm-gap', `${GAP}px`);

  /* ------------------------------------------------------------- carga */
  function paintSlides() {
    [['prev', idx - 1], ['cur', idx], ['next', idx + 1]].forEach(([k, i]) => {
      if (k === 'cur' && flipped) return;   // mostrando el escaneo: no pisarlo con el arte
      const img = $(`.mm-slide.${k}`);
      const src = list[i] ? cardArt(list[i]) : '';
      img.hidden = !src;
      if (src && img.getAttribute('src') !== src) img.src = src;
    });
  }

  function paintInfo() {
    const total = items.reduce((a, i) => a + i.quantity, 0);
    const bySet = new Map();
    for (const i of items) {
      const k = i.set_code || '—';
      bySet.set(k, (bySet.get(k) || 0) + i.quantity);
    }
    copiesBtn.querySelector('b').textContent = total;
    pop.innerHTML = total
      ? [...bySet].map(([k, q]) =>
          `<div class="mm-pop-row"><span>${esc(k)}</span><b>${q}</b></div>`).join('')
      : '<div class="mm-pop-row mm-dim">Sin copias</div>';
    setPop(false);
    $('.mm-goal b').textContent = Number(card.target) || 1;
    $('.mm-hof b').textContent = card.rating ? card.rating : '—';

    // Reverso: la portada del grupo, si no hay la foto principal, si no la primera.
    const photos = items.flatMap((i) => i.photos || []);
    const p = photos.find((x) => x.is_cover) || photos.find((x) => x.is_primary) || photos[0];
    scan = p ? photoUrl(p, false) : null;
    if (scan) { const pre = new Image(); pre.src = scan; }   // precarga para que el giro no muestre un hueco
    if (flipped && !scan) restoreFace();
    else if (flipped) $('.mm-slide.cur').src = scan;
    paintTag();
  }

  async function load() {
    const my = ++seq;
    paintSlides();
    mm.classList.add('is-loading');
    const id = list[idx].id;
    let c, it;
    try {
      [c, it] = await Promise.all([api.card(id), api.byCard(id, openOpts)]);
    } catch (e) {
      if (isStale(token) || my !== seq) return;
      toast(e.message, true);
      if (!card) closeModal();
      return;
    }
    if (isStale(token) || my !== seq) return;
    card = c;
    items = it.data;
    if (!cardArt(list[idx])) { list[idx] = c; paintSlides(); }
    mm.classList.remove('is-loading');
    paintInfo();
    resetForm();
    loadVersions(my);
  }

  async function loadVersions(my) {
    const box = $('.mm-versions');
    box.innerHTML = '<div class="mm-note">Buscando versiones…</div>';
    let versions;
    try {
      ({ versions } = await api.versions(card.id));
    } catch (e) {
      if (my !== seq) return;
      box.innerHTML = `<div class="mm-note">No se pudieron cargar las versiones (${esc(e.message)}).</div>`;
      return;
    }
    if (my !== seq) return;
    if (!versions.length) {
      box.innerHTML = '<div class="mm-note">Sin versiones conocidas. Importá el set desde Mantenimiento.</div>';
      return;
    }
    // Cuántas copias hay de cada impresión: mismo código que arma desktop (set_code-number).
    const held = (code) => items
      .filter((i) => i.set_code && i.number && `${i.set_code}-${i.number}` === code)
      .reduce((a, i) => a + i.quantity, 0);
    const ordered = [...versions.filter((v) => v.is_current), ...versions.filter((v) => !v.is_current)];
    box.innerHTML = ordered.map((v) => {
      const n = held(v.code);
      return `<button type="button" class="mm-ver${v.is_current ? '' : ' reprint'}"
          data-product="${v.market_product_id}" title="${esc(v.set || '')}">
        ${v.image ? `<img src="${esc(v.image)}" alt="" loading="lazy" draggable="false">`
                  : '<span class="mm-noimg"></span>'}
        <span class="mm-ver-code">${esc(v.code || '')}${n ? ` <em>×${n}</em>` : ''}</span>
        <span class="mm-ver-price">${v.price != null ? esc(eur(v.price)) : '—'}</span>
      </button>`;
    }).join('');
    const byId = new Map(ordered.map((v) => [String(v.market_product_id), v]));
    box.querySelectorAll('.mm-ver').forEach((btn) => {
      btn.onclick = () => {
        box.querySelectorAll('.mm-ver').forEach((b) => b.classList.remove('picked'));
        btn.classList.add('picked');
        picked = byId.get(btn.dataset.product);
      };
    });
  }

  /* ----------------------------------------------- popover de copias */
  function setPop(open) {
    pop.hidden = !open;
    copiesBtn.setAttribute('aria-expanded', String(open));
  }
  copiesBtn.onclick = () => setPop(pop.hidden);
  const outside = (e) => {
    if (!e.target.closest('.mm-copies, .mm-popover')) setPop(false);
  };
  document.addEventListener('pointerdown', outside);
  onClose(() => document.removeEventListener('pointerdown', outside));

  /* ------------------------------------------------- swipe de la carta */
  function paintTag() {
    const tag = $('.mm-face-tag');
    tag.hidden = !scan;
    tag.textContent = flipped ? '⟲ Ver catálogo' : '⟲ Ver escaneo';
  }

  // Vuelve la carta del centro a su arte de catálogo, sin animar.
  function restoreFace() {
    const cur = $('.mm-slide.cur');
    flipped = false; flipBusy = false;
    cur.style.transition = ''; cur.style.transform = '';
    const art = list[idx] ? cardArt(list[idx]) : '';
    if (art) cur.src = art;
    paintTag();
  }

  // Giro en dos tiempos: la carta se gira hasta quedar de canto, se cambia la
  // imagen y termina de girar. Con una sola <img> no hace falta un reverso aparte.
  async function toggleFlip() {
    if (flipBusy || busy || !scan) return;
    flipBusy = true;
    const cur = $('.mm-slide.cur');
    const toScan = !flipped;
    cur.style.transition = 'transform .16s ease-in';
    cur.style.transform = 'rotateY(90deg)';
    await new Promise((r) => setTimeout(r, 160));
    if (isStale(token)) return;
    await new Promise((r) => {
      cur.onload = cur.onerror = () => r();
      cur.src = toScan ? scan : cardArt(list[idx]);
      if (cur.complete) r();
    });
    flipped = toScan;
    paintTag();
    cur.style.transition = 'transform .16s ease-out';
    cur.style.transform = 'rotateY(0deg)';
    await new Promise((r) => setTimeout(r, 170));
    cur.style.transition = ''; cur.style.transform = '';
    flipBusy = false;
  }

  let snapTimer = 0;
  function snapBack() {
    track.style.transition = 'transform .18s ease-out';
    track.style.transform = 'translateX(0)';
    clearTimeout(snapTimer);
    snapTimer = setTimeout(() => mm.classList.remove('swiping'), 190);
  }

  // Los tres <img> cambian de rol en lugar de recargar sus src: reasignar el src
  // del que queda en el centro dejaba un cuadro con la carta anterior a la vista.
  function rotate(dir) {
    const p = $('.mm-slide.prev'), c = $('.mm-slide.cur'), n = $('.mm-slide.next');
    if (dir > 0) {
      p.className = 'mm-slide next'; c.className = 'mm-slide prev'; n.className = 'mm-slide cur';
    } else {
      n.className = 'mm-slide prev'; c.className = 'mm-slide next'; p.className = 'mm-slide cur';
    }
  }

  function go(dir) {
    const target = idx + dir;
    if (busy || target < 0 || target >= list.length) return snapBack();
    busy = true;
    track.style.transition = 'transform .22s ease-out';
    track.style.transform = `translateX(${-dir * (track.clientWidth + GAP)}px)`;
    // setTimeout y no transitionend: no depende de que la transición llegue a disparar.
    setTimeout(() => {
      if (flipped) restoreFace();   // la carta que sale vuelve a su arte antes de reciclarse
      idx = target;
      rotate(dir);
      track.style.transition = 'none';
      track.style.transform = 'translateX(0)';
      mm.classList.remove('swiping');   // las vecinas vuelven a quedar ocultas en reposo
      busy = false;
      load();   // solo repinta el <img> reciclado, que está fuera de pantalla
    }, 230);
  }

  (function wireSwipe() {
    let drag = false, locked = null, x0 = 0, y0 = 0, dx = 0, dy = 0, t0 = 0;
    stage.addEventListener('pointerdown', (e) => {
      if (busy || sheet.dataset.state === 'open') return;
      drag = true; locked = null; dx = dy = 0;
      clearTimeout(snapTimer);
      mm.classList.add('swiping');
      x0 = e.clientX; y0 = e.clientY; t0 = performance.now();
      stage.setPointerCapture(e.pointerId);
      track.style.transition = 'none';
    });
    stage.addEventListener('pointermove', (e) => {
      if (!drag) return;
      dx = e.clientX - x0; dy = e.clientY - y0;
      if (locked === null && Math.hypot(dx, dy) > 8) {
        locked = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
      }
      if (locked !== 'x') return;
      const edge = (dx > 0 && idx === 0) || (dx < 0 && idx === list.length - 1);
      track.style.transform = `translateX(${edge ? dx * 0.25 : dx}px)`;   // resistencia en los extremos
    });
    const end = () => {
      if (!drag) return;
      drag = false;
      const v = dx / Math.max(1, performance.now() - t0);
      const w = stage.clientWidth;
      if (locked === 'x') {
        if (dx < -w * SWIPE_FRAC || v < -FLICK_V) return go(1);
        if (dx > w * SWIPE_FRAC || v > FLICK_V) return go(-1);
        return snapBack();
      }
      mm.classList.remove('swiping');
      if (locked === null && performance.now() - t0 < 400) return toggleFlip();   // toque: girar
      if (locked === 'y' && dy < -50) setSheet(true);   // swipe up sobre la carta también abre el panel
    };
    stage.addEventListener('pointerup', end);
    stage.addEventListener('pointercancel', () => { drag = false; snapBack(); });
  })();

  /* --------------------------------------------------- panel inferior */
  function setSheet(open) {
    sheet.style.height = '';
    sheet.classList.remove('dragging');
    sheet.dataset.state = open ? 'open' : 'peek';
    mm.classList.toggle('sheet-open', open);
    if (!open) $('.mm-sheet-body').scrollTop = 0;
  }

  (function wireSheet() {
    const handle = $('.mm-handle');
    let drag = false, moved = false, y0 = 0, h0 = 0, t0 = 0, peekPx = 0, h = 0;
    handle.addEventListener('pointerdown', (e) => {
      drag = true; moved = false;
      y0 = e.clientY; t0 = performance.now();
      h0 = sheet.offsetHeight;
      if (sheet.dataset.state === 'peek') peekPx = h0;
      h = h0;
      handle.setPointerCapture(e.pointerId);
    });
    handle.addEventListener('pointermove', (e) => {
      if (!drag) return;
      const dy = e.clientY - y0;
      if (!moved && Math.abs(dy) > 6) { moved = true; sheet.classList.add('dragging'); }
      if (!moved) return;
      const openPx = Math.round(window.innerHeight * OPEN_FRAC);
      h = Math.min(openPx, Math.max(peekPx, h0 - dy));
      sheet.style.height = `${h}px`;
    });
    const end = (e) => {
      if (!drag) return;
      drag = false;
      if (!moved) return setSheet(sheet.dataset.state !== 'open');   // tap
      const v = (y0 - e.clientY) / Math.max(1, performance.now() - t0);
      const mid = (peekPx + window.innerHeight * OPEN_FRAC) / 2;
      setSheet(v > 0.4 ? true : v < -0.4 ? false : h > mid);
    };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', () => { drag = false; setSheet(sheet.dataset.state === 'open'); });
  })();

  /* ----------------------------------------------------- formulario */
  const qty = $('[name=quantity]');
  $$('.mm-qty button').forEach((b) => {
    b.onclick = () => { qty.value = Math.max(1, (Number(qty.value) || 1) + Number(b.dataset.d)); };
  });
  $$('.mm-chip').forEach((chip) => {
    chip.onclick = () => {
      $$('.mm-chip').forEach((c) => c.classList.remove('on'));
      chip.classList.add('on');
      condition = chip.dataset.cond;
    };
  });
  const photoInput = $('.mm-photo-input'), photoBtn = $('.mm-photo');
  photoBtn.onclick = () => photoInput.click();
  photoInput.onchange = () => {
    pendingPhoto = photoInput.files[0] || null;
    photoBtn.textContent = pendingPhoto ? '✓ Foto' : 'Foto';
    photoBtn.classList.toggle('on', !!pendingPhoto);
  };

  function resetForm() {
    picked = null; pendingPhoto = null;
    condition = META.conditions[0].key;
    qty.value = 1;
    photoInput.value = '';
    photoBtn.textContent = 'Foto';
    photoBtn.classList.remove('on');
    $$('.mm-chip').forEach((c, i) => c.classList.toggle('on', i === 0));
    $$('.mm-ver').forEach((b) => b.classList.remove('picked'));
  }

  $('.mm-cancel').onclick = () => { resetForm(); setSheet(false); };
  $('.mm-close').onclick = closeModal;

  $('.mm-save').onclick = async (e) => {
    if (!picked) { toast('Elegí una versión de Cardmarket', true); return; }
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      const newItem = await api.addItem({
        card_id: picked.card_id || card.id,
        language: $('[name=language]').value,
        condition,
        quantity: Math.max(1, Number(qty.value) || 1),
        market_product_id: Number(picked.market_product_id),
      });
      if (pendingPhoto && newItem?.id) {
        try { await api.uploadPhoto(newItem.id, pendingPhoto); }
        catch (err) { toast('Carta guardada pero falló la foto: ' + err.message, true); }
      }
      toast(`${card.name} añadida`);
      ctx.onChange();
      setSheet(false);
      await load();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
    }
  };

  await load();
}