import { QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { createHashRouter, Navigate, RouterProvider } from 'react-router';

import { queryClient } from '@/api/queryClient';
import { AppShell } from '@/components/layout/AppShell';
import { EmptyState } from '@/components/ui/EmptyState';
import { CardModalProvider } from '@/context/CardModalContext';
import { MetaProvider } from '@/context/MetaContext';
import { ToastProvider } from '@/context/ToastContext';
import { CollectionPage } from '@/features/collection/CollectionPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { MissingPage } from '@/features/missing/MissingPage';
import { SetDetailPage } from '@/features/sets/SetDetailPage';
import { SetsPage } from '@/features/sets/SetsPage';

// Desktop-only and rarely opened, so it stays out of the main bundle.
const MaintenancePage = lazy(() =>
  import('@/features/maintenance/MaintenancePage').then((module) => ({
    default: module.MaintenancePage,
  })),
);

/* Hash routes, so every existing bookmark and the installed home-screen app
   (`#/sets`, `#/set/<id>`, …) keep resolving, and Flask only ever serves `/`. */
const router = createHashRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'sets', element: <SetsPage /> },
      { path: 'set/:setId', element: <SetDetailPage /> },
      { path: 'cartas', element: <CollectionPage /> },
      { path: 'collection', element: <CollectionPage /> },
      { path: 'missing/:setId?', element: <MissingPage /> },
      {
        path: 'mantenimiento',
        element: (
          <Suspense fallback={<EmptyState>Cargando…</EmptyState>}>
            <MaintenancePage />
          </Suspense>
        ),
      },
      { path: '*', element: <Navigate to="/dashboard" replace /> },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MetaProvider>
          <CardModalProvider>
            <RouterProvider router={router} />
          </CardModalProvider>
        </MetaProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
