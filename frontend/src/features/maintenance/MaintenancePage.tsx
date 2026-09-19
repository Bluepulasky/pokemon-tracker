import type { ReactNode } from 'react';

import { AsyncView } from '@/components/ui/AsyncView';
import { PageTitle, SectionTitle, Subtitle } from '@/components/ui/typography';

import { CardMetaFixes } from './sections/CardMetaFixes';
import { EpisodeBrowser } from './sections/EpisodeBrowser';
import { HealthReport } from './sections/HealthReport';
import { HiddenSets } from './sections/HiddenSets';
import { BudgetPanels, JobState } from './sections/JobPanels';
import { ModifiersEditor } from './sections/ModifiersEditor';
import { PriceJobs } from './sections/PriceJobs';
import { TargetsImport } from './sections/TargetsImport';
import { useJobStatus } from './useJobStatus';

export function MaintenancePage() {
  const job = useJobStatus();

  return (
    <AsyncView queries={[job]}>
      <PageTitle>Mantenimiento</PageTitle>
      <Subtitle>Tareas que hablan con fuentes externas y tardan minutos.</Subtitle>
      <PriceJobs />

      <Section
        title="Objetivos por lote"
        intro="Cuántas copias querés de cada carta, desde un CSV. Descargá el actual, editá la columna y volvé a subirlo."
      >
        <TargetsImport />
      </Section>

      <Section
        title="Correcciones de datos"
        intro="Corrige datos de las cartas — ilustrador, tipo (Pokémon/Trainer/Energy) y color — que quedaron vacíos, sin volver a importar ni gastar consultas. Se cruza por card_id."
      >
        <CardMetaFixes />
      </Section>

      <Section
        title="Revisión de datos"
        intro="Busca desajustes de vocabulario — un grado renombrado, una rareza escrita de dos formas — que no dan error y sí dan números mal."
      >
        <HealthReport />
      </Section>

      <Section
        title="Consultas a la API"
        intro="Las últimas 24 horas, moviéndose contigo — no se reinicia a medianoche, porque no sabemos a qué hora se reinicia la del plan."
      >
        <BudgetPanels budgets={job.data?.budgets ?? []} />
      </Section>

      <Section title="Estado">{job.data && <JobState job={job.data} />}</Section>

      <Section
        title="Multiplicadores de precio"
        intro="El precio de una impresión se ajusta por la condición de la carta."
      >
        <ModifiersEditor />
      </Section>

      <Section
        title="Sets ocultos"
        intro="Sets que ocultaste de la colección con la ✕. Siguen importados y no cuentan para el progreso; mostralos de nuevo acá."
      >
        <HiddenSets />
      </Section>

      <Section
        title="DB Sets"
        intro="Buscá un set y añadilo. Trae sus cartas, sus versiones y sus precios de una vez; después no cuesta consultas abrirlas."
      >
        <EpisodeBrowser />
      </Section>
    </AsyncView>
  );
}

function Section({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: string;
  children: ReactNode;
}) {
  return (
    <section>
      <SectionTitle>{title}</SectionTitle>
      {intro && <Subtitle className="mb-2.5">{intro}</Subtitle>}
      {children}
    </section>
  );
}
