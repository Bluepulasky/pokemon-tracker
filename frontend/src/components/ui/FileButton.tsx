import { useRef, type ReactNode } from 'react';

import { Button } from './Button';

interface Props {
  children: ReactNode;
  accept: string;
  onFile: (file: File) => void;
  variant?: 'default' | 'primary';
  size?: 'md' | 'xs';
  disabled?: boolean;
}

/** A button that opens the file picker and hands back the chosen file. */
export function FileButton({ children, accept, onFile, variant, size, disabled }: Props) {
  const input = useRef<HTMLInputElement>(null);

  return (
    <>
      <Button
        variant={variant}
        size={size}
        disabled={disabled}
        onClick={() => input.current?.click()}
      >
        {children}
      </Button>
      <input
        ref={input}
        type="file"
        accept={accept}
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          // Cleared so picking the same file twice in a row fires again.
          event.target.value = '';
          if (file) onFile(file);
        }}
      />
    </>
  );
}
