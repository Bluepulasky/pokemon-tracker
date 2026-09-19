import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

type Variant = 'default' | 'primary' | 'ghost' | 'danger';
type Size = 'md' | 'xs';

interface StyleProps {
  variant?: Variant;
  size?: Size;
  className?: string;
}

const VARIANTS: Record<Variant, string> = {
  default: 'border-line bg-surface-3 hover:border-fg-faint',
  primary: 'border-accent bg-accent text-accent-ink hover:brightness-110',
  ghost: 'border-line bg-transparent hover:border-fg-faint',
  danger: 'border-bad/35 bg-surface-3 text-bad hover:border-bad',
};

const SIZES: Record<Size, string> = {
  md: 'px-4.5 py-2.5 font-semibold',
  xs: 'px-2.5 py-1.5 text-xs font-medium',
};

/** The classes of a button, for elements that are not a `<button>`. */
// eslint-disable-next-line react-refresh/only-export-components
export function buttonClasses({ variant = 'default', size = 'md', className }: StyleProps = {}) {
  return cn(
    'inline-flex items-center justify-center rounded-control border transition',
    'disabled:cursor-not-allowed disabled:opacity-50',
    VARIANTS[variant],
    SIZES[size],
    className,
  );
}

type ButtonProps = StyleProps & ButtonHTMLAttributes<HTMLButtonElement>;

export function Button({ variant, size, className, type = 'button', ...rest }: ButtonProps) {
  return <button type={type} className={buttonClasses({ variant, size, className })} {...rest} />;
}

type ButtonLinkProps = StyleProps & AnchorHTMLAttributes<HTMLAnchorElement>;

/** A link that looks like a button, e.g. a file download. */
export function ButtonLink({ variant, size, className, ...rest }: ButtonLinkProps) {
  return <a className={buttonClasses({ variant, size, className })} {...rest} />;
}
