import { cn } from '@/lib/cn';

interface Props {
  src?: string | null;
  className?: string;
}

/** A set logo, or a grey block of the same size when there is none. */
export function LogoImage({ src, className }: Props) {
  if (!src) return <div className={cn('rounded-sm bg-gray-500/15', className)} />;
  return <img src={src} alt="" loading="lazy" className={cn('object-contain', className)} />;
}
