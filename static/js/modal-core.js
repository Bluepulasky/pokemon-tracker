/* Estado y utilidades compartidas entre modal-desktop.js y modal-mobile.js.
   Nada de markup acá: solo lo que ambos necesitan para abrir y cerrar. */

export const ctx = { META: null, onChange: () => {} };

// Cada apertura toma un token; closeModal() lo invalida, así una carga en vuelo
// no repinta un modal que ya se cerró ni pisa a una apertura más nueva.
let token = 0;
export const nextToken = () => ++token;
export const isStale = (t) => t !== token;

// Limpiezas (listeners de teclado, de documento…) que corren al cerrar.
const cleanups = new Set();
export const onClose = (fn) => { cleanups.add(fn); };

export const lockScroll = (on) =>
  document.documentElement.classList.toggle('modal-open', on);

export const isMobile = () => window.matchMedia('(max-width: 600px)').matches;

export function closeModal() {
  token++;
  cleanups.forEach((fn) => fn());
  cleanups.clear();
  const root = document.getElementById('modal-root');
  document.querySelector('.sort-select')?.style.setProperty('display', '');
  lockScroll(false);
  root.hidden = true;
  root.classList.remove('is-mobile');
  root.innerHTML = '';
}
