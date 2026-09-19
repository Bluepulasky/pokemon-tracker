import { Link } from 'react-router';

import type { SetProgress } from '@/api/types';
import { Panel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { pct } from '@/lib/format';

interface Props {
  set: SetProgress;
  /** Shows the × that hides the set from the collection. */
  onHide?: (setId: string) => void;
}

/** A set's progress summary, linking to its detail page. */
export function SetCard({ set, onHide }: Props) {
  const missing = set.missing ?? set.target - set.owned;

  return (
    <Panel className="relative transition hover:-translate-y-0.5 hover:border-accent-2">
      {onHide && (
        <button
          type="button"
          title="Ocultar de la colección (se puede mostrar desde Mantenimiento)"
          onClick={() => onHide(set.id)}
          className="absolute top-1.5 right-2 z-10 px-1.5 py-0.5 text-lg leading-none text-fg-faint opacity-40 transition hover:text-bad hover:opacity-100"
        >
          ×
        </button>
      )}
      {/* The link covers the panel; the hide button sits above it. */}
      <Link to={`/set/${set.id}`} className="block after:absolute after:inset-0">
        <span className="float-right mr-5 font-semibold tabular-nums">
          {pct(set.completion_pct)}
        </span>
        {set.logo_url && (
          <img
            src={set.logo_url}
            alt=""
            loading="lazy"
            className="mb-2 block h-6 max-w-[60%] object-contain object-left"
          />
        )}
        <div className="mb-0.5 font-semibold">{set.name}</div>
        <div className="text-[13px] text-fg-dim">
          {set.owned} / {set.target} cartas{missing > 0 && ` · faltan ${missing}`}
        </div>
        <ProgressBar value={set.owned} max={set.target} />
      </Link>
    </Panel>
  );
}

export function SetGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-3">{children}</div>
  );
}
