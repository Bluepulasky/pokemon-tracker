import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router';

import { useCardModal } from '@/context/CardModalContext';
import { CardModal } from '@/features/card-modal/CardModal';

import { Topbar } from './Topbar';

/** Header, the routed page, and the card modal over both. */
export function AppShell() {
  const { pathname, search } = useLocation();
  const { close } = useCardModal();

  // Leaving a route (or changing its filters) dismisses the modal, or it
  // lingers over the new view.
  useEffect(() => {
    return () => close();
  }, [pathname, search, close]);

  // A new page starts at the top; a filter change on the same page does not move.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <>
      <Topbar />
      <main className="mx-auto max-w-350 px-3 pt-4 pb-16 md:px-4 md:pt-6 md:pb-20">
        <Outlet />
      </main>
      <CardModal />
    </>
  );
}
