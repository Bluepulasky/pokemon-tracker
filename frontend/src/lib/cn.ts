import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Joins class names, dropping falsy ones. Where two utilities set the same
 * property the later one wins, so a component's `className` prop can override
 * its defaults (`w-full` + `w-24` → `w-24`).
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
