import { api } from '@/api/client';
import type { TargetImportResult } from '@/api/types';
import { ButtonLink } from '@/components/ui/Button';
import { FileButton } from '@/components/ui/FileButton';
import { Panel } from '@/components/ui/Panel';
import { ErrorText, ResultDetail, ResultSummary } from '@/components/ui/ResultBox';
import { Note } from '@/components/ui/typography';
import { useApiMutation } from '@/hooks/useApiMutation';

/** Bulk copy targets: download the CSV, edit a column, upload it back. */
export function TargetsImport() {
  const upload = useApiMutation(api.importTargets);

  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-2">
        <ButtonLink href={api.targetsExportUrl} download>
          Descargar CSV actual
        </ButtonLink>
        <FileButton variant="primary" accept=".csv,text/csv" onFile={upload.mutate}>
          Subir CSV
        </FileButton>
      </div>
      <Note>
        Columnas: <code>card_id</code>, <code>card_name</code> (referencia),{' '}
        <code>target_quantity</code>. El objetivo es de la carta, así que vale en todos los sets
        donde aparezca. No exporta los sets hidden.
      </Note>
      {upload.isPending && <Note>Procesando…</Note>}
      {upload.error && <ErrorText>{upload.error.message}</ErrorText>}
      {upload.data && <TargetsResult result={upload.data} />}
    </Panel>
  );
}

/** Leads with what changed; every rejected row keeps its line number. */
function TargetsResult({ result }: { result: TargetImportResult }) {
  const changes = result.changes ?? [];
  const problems = result.problems ?? [];

  return (
    <>
      <ResultSummary tone={result.errors ? 'partial' : 'ok'}>
        <strong>{result.updated}</strong> actualizados · {result.unchanged} sin cambios ·{' '}
        <span className={result.errors ? 'text-bad' : undefined}>
          {result.errors} con problemas
        </span>
      </ResultSummary>
      {changes.length > 0 && (
        <ResultDetail summary={`Cambios (${result.updated})`}>
          <ul className="list-disc pl-5">
            {changes.map((change) => (
              <li key={change.card_id}>
                <code>{change.card_id}</code> {change.from} → <strong>{change.to}</strong>
              </li>
            ))}
          </ul>
        </ResultDetail>
      )}
      {problems.length > 0 && (
        <ResultDetail summary={`Problemas (${result.errors})`} defaultOpen>
          <ul className="list-disc pl-5 text-bad">
            {problems.map((problem) => (
              <li key={problem.line}>
                línea {problem.line}
                {problem.card_id && (
                  <>
                    {' · '}
                    <code>{problem.card_id}</code>
                  </>
                )}{' '}
                — {problem.error}
              </li>
            ))}
          </ul>
        </ResultDetail>
      )}
    </>
  );
}
