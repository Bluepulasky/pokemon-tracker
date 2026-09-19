import { useState, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

export interface AccordionSection {
  id: string;
  title: ReactNode;
  content: ReactNode;
}

interface Props {
  sections: readonly AccordionSection[];
  /** Section open at first; `null` for all closed. */
  defaultOpen: string | null;
  className?: string;
}

/** Collapsible sections where at most one is open. */
export function Accordion({ sections, defaultOpen, className }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={className}>
      {sections.map((section) => {
        const isOpen = open === section.id;
        return (
          <section key={section.id} className="border-b border-line px-5 py-2">
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => setOpen(isOpen ? null : section.id)}
              className="flex w-full items-center gap-3 py-4.5 text-left font-semibold select-none hover:text-accent"
            >
              <span className={cn('text-[10px] transition-transform', isOpen && 'rotate-90')}>
                ▶
              </span>
              {section.title}
            </button>
            {isOpen && <div className="pb-5.5">{section.content}</div>}
          </section>
        );
      })}
    </div>
  );
}
