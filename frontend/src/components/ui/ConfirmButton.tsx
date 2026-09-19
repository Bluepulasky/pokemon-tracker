import { useState, type ReactNode } from 'react';

import { Button } from './Button';

interface Props {
  children: ReactNode;
  /** Label once armed, e.g. "Confirmar — gasta ~12 consultas". */
  confirmLabel: ReactNode;
  /** Label while `busy`. */
  busyLabel?: ReactNode;
  busy?: boolean;
  onConfirm: () => void;
  size?: 'md' | 'xs';
  className?: string;
}

/** Two-step button: the first click arms it, the second runs `onConfirm`. No dialog. */
export function ConfirmButton({
  children,
  confirmLabel,
  busyLabel,
  busy = false,
  onConfirm,
  size,
  className,
}: Props) {
  const [armed, setArmed] = useState(false);

  const handleClick = () => {
    if (!armed) {
      setArmed(true);
      return;
    }
    setArmed(false);
    onConfirm();
  };

  return (
    <Button
      size={size}
      className={className}
      variant={armed ? 'danger' : 'default'}
      disabled={busy}
      onClick={handleClick}
      onBlur={() => setArmed(false)}
    >
      {busy ? (busyLabel ?? children) : armed ? confirmLabel : children}
    </Button>
  );
}
