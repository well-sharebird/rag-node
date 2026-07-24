import React from 'react';
import { cn } from '@/lib/utils';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'neutral';
  size?: 'sm' | 'md';
  children: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = 'neutral',
  size = 'md',
  children,
  ...props
}) => {
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full whitespace-nowrap',
        variant === 'primary' && 'bg-[var(--bird-primary-100)] text-[var(--bird-primary-700)]',
        variant === 'secondary' && 'bg-[var(--bird-neutral-100)] text-[var(--bird-text-secondary)]',
        variant === 'success' && 'bg-[var(--bird-success-bg)] text-[var(--bird-success)]',
        variant === 'warning' && 'bg-[var(--bird-warning-bg)] text-[var(--bird-warning)]',
        variant === 'error' && 'bg-[var(--bird-error-bg)] text-[var(--bird-error)]',
        variant === 'neutral' && 'bg-[var(--bird-neutral-100)] text-[var(--bird-text-secondary)]',
        size === 'sm' && 'px-1.5 py-0.5 text-[10px]',
        size === 'md' && 'px-2 py-0.5',
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
