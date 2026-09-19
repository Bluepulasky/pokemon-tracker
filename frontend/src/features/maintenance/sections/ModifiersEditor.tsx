import { useQuery } from '@tanstack/react-query';

import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { Input } from '@/components/ui/controls';
import { Panel, PanelLabel } from '@/components/ui/Panel';
import { useApiMutation } from '@/hooks/useApiMutation';

interface ModifierChange {
  kind: string;
  key: string;
  multiplier: number;
}

/** The price multipliers, one panel per kind; a value saves when its input is left. */
export function ModifiersEditor() {
  const { data } = useQuery({ queryKey: queryKeys.modifiers, queryFn: api.modifiers });
  const save = useApiMutation(
    ({ kind, key, multiplier }: ModifierChange) => api.setModifier(kind, key, multiplier),
    { success: (_result, change) => `${change.key}: ×${change.multiplier}` },
  );

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-3">
      {Object.entries(data ?? {}).map(([kind, rows]) => (
        <Panel key={kind}>
          <PanelLabel>{kind}</PanelLabel>
          {Object.entries(rows).map(([key, value]) => (
            <label key={key} className="my-1.5 flex items-center gap-2">
              <span className="flex-1">{key}</span>
              <Input
                type="number"
                step={0.05}
                min={0.05}
                defaultValue={value}
                className="w-22.5 px-2 py-1.5"
                onBlur={(event) => {
                  const multiplier = Number(event.target.value);
                  if (multiplier !== value) save.mutate({ kind, key, multiplier });
                }}
              />
            </label>
          ))}
        </Panel>
      ))}
    </div>
  );
}
