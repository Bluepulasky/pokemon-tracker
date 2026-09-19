import { useState, type ReactNode } from 'react';

import { Field } from './controls';

interface Props {
  label: ReactNode;
  min: number;
  max: number;
  value: number;
  /** Text shown next to the label for the value under the thumb. */
  display: (value: number) => ReactNode;
  /** Called once per gesture, when the thumb is released — not while dragging. */
  onCommit: (value: number) => void;
}

/** A slider that previews its value while dragging and reports it on release. */
export function RangeField({ label, min, max, value, display, onCommit }: Props) {
  const [draft, setDraft] = useState(value);
  const commit = () => {
    if (draft !== value) onCommit(draft);
  };

  return (
    <Field label={label} aside={display(draft)} className="flex-1">
      <input
        type="range"
        min={min}
        max={max}
        step={1}
        value={draft}
        onChange={(event) => setDraft(Number(event.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={commit}
      />
    </Field>
  );
}
