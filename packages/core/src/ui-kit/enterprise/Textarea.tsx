import { TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export function Textarea({ className, error, ...props }: TextareaProps) {
  return (
    <textarea
      className={cn(
        'w-full px-3 py-2 border rounded-lg text-sm',
        'transition-colors duration-200',
        'focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        error
          ? 'border-red-500 focus:ring-red-500'
          : 'border-[var(--gray-300)] hover:border-[var(--gray-400)] bg-[var(--input-bg)] text-[var(--text-primary)]',
        className
      )}
      {...props}
    />
  );
}
