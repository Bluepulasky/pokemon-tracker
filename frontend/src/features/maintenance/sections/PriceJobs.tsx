import { useQueryClient } from '@tanstack/react-query';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { Button } from '@/components/ui/Button';
import { ConfirmButton } from '@/components/ui/ConfirmButton';
import { Panel, PanelLabel } from '@/components/ui/Panel';
import { Note } from '@/components/ui/typography';
import { useApiMutation } from '@/hooks/useApiMutation';

/** The two long-running jobs: re-price the collection, and sync the tcggo set list. */
export function PriceJobs() {
  const client = useQueryClient();

  // Starting the job invalidates the cached reads, the job status among them,
  // so the Estado panel picks the run up and polls it from there.
  const refresh = useApiMutation(api.refreshPricesAsync);
  const sync = useApiMutation(api.syncCatalog, {
    success: (result) =>
      `Catálogo sincronizado: ${result.synced} sets. Ya podés buscarlos sin gastar consultas.`,
    // The set list is local now, so re-listing it costs nothing.
    onDone: () => void client.invalidateQueries({ queryKey: queryKeys.episodes('').slice(0, 1) }),
  });

  return (
    <div className="mt-2.5 grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3">
      <Panel>
        <PanelLabel>Actualizar precios</PanelLabel>
        <Note>
          Vuelve a consultar el precio de cada impresión que tenés. Los precios manuales no se
          tocan.
        </Note>
        <Button
          variant="primary"
          className="mt-4"
          disabled={refresh.isPending}
          onClick={() => refresh.mutate()}
        >
          Actualizar precios ahora
        </Button>
      </Panel>

      <Panel>
        <PanelLabel>Sincronizar lista de sets</PanelLabel>
        <Note>
          Descarga el catálogo completo de sets para poder buscarlos al instante y sin conexión.{' '}
          <strong className="text-warn">⚠ Gasta ~12 consultas de la API</strong> — hacelo una sola
          vez.
        </Note>
        <ConfirmButton
          className="mt-4"
          confirmLabel="Confirmar — gasta ~12 consultas"
          busyLabel="Sincronizando…"
          busy={sync.isPending}
          onConfirm={() => sync.mutate()}
        >
          Sincronizar lista de sets
        </ConfirmButton>
      </Panel>
    </div>
  );
}
