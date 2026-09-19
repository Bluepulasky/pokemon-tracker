import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';

import type { Option } from '@/api/types';
import { cn } from '@/lib/cn';

type ControlSize = 'toolbar' | 'field';

const CONTROL_BASE =
  'border-line bg-surface-3 rounded-control focus:border-accent-2 border outline-none';

const CONTROL_SIZES: Record<ControlSize, string> = {
  toolbar: 'px-2.5 py-1.5',
  field: 'w-full px-3 py-2',
};

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'onChange' | 'size'> {
  options: readonly Option[];
  value: string;
  onChange: (value: string) => void;
  /** Label of the blank first option. Omit for a select that always has a value. */
  placeholder?: string;
  size?: ControlSize;
}

export function Select({
  options,
  value,
  onChange,
  placeholder,
  size = 'toolbar',
  className,
  ...rest
}: SelectProps) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className={cn(CONTROL_BASE, CONTROL_SIZES[size], className)}
      {...rest}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((option) => (
        <option key={option.key} value={option.key}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  size?: ControlSize;
}

export function Input({ size = 'field', className, ...rest }: InputProps) {
  return <input className={cn(CONTROL_BASE, CONTROL_SIZES[size], className)} {...rest} />;
}

interface FieldProps {
  label: ReactNode;
  /** Shown at the right end of the label row, e.g. a slider's current value. */
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** The caption above a control or a group of them. */
export function FieldLabel({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <span className="mb-1.5 flex items-center justify-between text-xs tracking-wider text-fg-faint uppercase">
      {children}
      {aside}
    </span>
  );
}

/** A single labelled form control. */
export function Field({ label, aside, className, children }: FieldProps) {
  return (
    <label className={cn('block min-w-0', className)}>
      <FieldLabel aside={aside}>{label}</FieldLabel>
      {children}
    </label>
  );
}

/** Turns plain strings into select options. */
// eslint-disable-next-line react-refresh/only-export-components
export function toOptions(values: readonly string[]): Option[] {
  return values.map((value) => ({ key: value, label: value }));
}
