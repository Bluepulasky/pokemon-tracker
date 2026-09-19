import { useState } from 'react';

import { api } from '@/api/client';
import type { CardMetaResult } from '@/api/types';
import { Button, ButtonLink } from '@/components/ui/Button';
import { FileButton } from '@/components/ui/FileButton';
import { Panel } from '@/components/ui/Panel';
import { ErrorText, ResultDetail, ResultSummary } from '@/components/ui/ResultBox';
import { Note } from '@/components/ui/typography';
import { useApiMutation } from '@/hooks/useApiMutation';

/** Fills artist, supertype and colour from the bundled CSV or one the user uploads. */
export function CardMetaFixes() {
  const [overwrite, setOverwrite] = useState(false);

  const run = useApiMutation((file: File | null) =>
    file ? api.importCardMeta(file, overwrite) : api.applyCardMeta(overwrite),
  );

  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={run.isPending} onClick={() => run.mutate(null)}>
          Aplicar correcciones incluidas
        </Button>
        <ButtonLink href={api.cardMetaExportUrl} download>
          Descargar CSV actual
        </ButtonLink>
        <FileButton accept=".csv,text/csv" disabled={run.isPending} onFile={run.mutate}>
          Subir CSV propio
        </FileButton>
      </div>

      <label className="mt-2.5 flex items-center gap-1.5">
        <input
          type="checkbox"
          className="accent-accent"
          checked={overwrite}
          onChange={(event) => setOverwrite(event.target.checked)}
        />
        <span>
          Sobrescribir valores existentes{' '}
          <span className="text-xs text-fg-faint">(por defecto solo rellena los vacíos)</span>
        </span>
      </label>

      <Note>
        «Aplicar correcciones incluidas» usa el archivo que viene con la app; «Subir CSV propio»
        aplica el tuyo al instante. Columnas: <code>card_id</code> + <code>artist</code>,{' '}
        <code>supertype</code> (Pokémon / Trainer / Energy), <code>types</code> (el color: Fire,
        Water…; dos tipos separados por <code>|</code>). Celda vacía = no toca ese campo. Ambas
        acciones respetan la casilla de arriba. El color solo llega por acá: tcggo no lo trae, así
        que un set recién importado no tiene color hasta aplicar el archivo.
      </Note>

      {run.isPending && <Note>Aplicando…</Note>}
      {run.error && <ErrorText>{run.error.message}</ErrorText>}
      {run.data && <MetaResult result={run.data} />}
    </Panel>
  );
}

/** Headline: how many gaps were closed per field. Unknown ids are listed, not swallowed. */
function MetaResult({ result }: { result: CardMetaResult }) {
  const changed = Object.entries(result.changed ?? {});
  const total = changed.reduce((sum, [, count]) => sum + count, 0);
  const nothing = result.overwrite
    ? 'Nada que cambiar (los valores ya coincidían)'
    : 'Nada que rellenar (no había campos vacíos)';

  return (
    <>
      <ResultSummary tone={result.unknown ? 'partial' : 'ok'}>
        {total === 0 ? (
          nothing
        ) : (
          <>
            {result.overwrite ? 'Sobrescrito' : 'Rellenado'}:{' '}
            {changed.map(([field, count], index) => (
              <span key={field}>
                {index > 0 && ' · '}
                <strong>{count}</strong> {field}
              </span>
            ))}
          </>
        )}
        {result.unknown > 0 && (
          <span className="text-bad"> · {result.unknown} id(s) desconocidos</span>
        )}
      </ResultSummary>
      {result.unknown > 0 && (
        <ResultDetail summary={`Ids no encontrados en tu catálogo (${result.unknown})`}>
          <Note>
            {(result.unknown_ids ?? []).join(', ')}
            {result.unknown > 50 && ' …'}
          </Note>
        </ResultDetail>
      )}
    </>
  );
}
