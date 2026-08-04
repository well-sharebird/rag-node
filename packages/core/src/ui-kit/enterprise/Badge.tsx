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
        variant === 'primary' && 'bg-[var(--accent-light)] text-[var(--accent)]',
        variant === 'secondary' && 'bg-[var(--gray-100)] text-[var(--text-secondary)]',
        variant === 'success' && 'bg-[var(--success-bg)] text-[var(--success)]',
        variant === 'warning' && 'bg-[var(--warning-bg)] text-[var(--warning)]',
        variant === 'error' && 'bg-[var(--error-bg)] text-[var(--error)]',
        variant === 'neutral' && 'bg-[var(--gray-100)] text-[var(--text-secondary)]',
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
