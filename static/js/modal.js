/* Punto de entrada del modal de carta. Los imports existentes
   (initModal, closeModal, openCard) siguen apuntando a './modal.js'. */
import { ctx, closeModal, isMobile } from './modal-core.js';
import { initDesktop, openCardDesktop } from './modal-desktop.js';
import { openCardMobile } from './modal-mobile.js';

export { closeModal };

export function initModal(meta, changeHandler) {
  ctx.META = meta;
  ctx.onChange = changeHandler;
  initDesktop(meta, changeHandler);
  document.getElementById('modal-root').addEventListener('click', (e) => {
    if (e.target.id === 'modal-root') closeModal();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
}

// Se decide al abrir, no en vivo: rotar el teléfono con el modal abierto no lo reconstruye.
export const openCard = (cardId, opts = {}) =>
  (isMobile() ? openCardMobile : openCardDesktop)(cardId, opts);
