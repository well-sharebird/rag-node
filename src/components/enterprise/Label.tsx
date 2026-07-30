import React from 'react';
import { cn } from '@/lib/utils';

export interface LabelProps extends React.LabelHTMLAttributes<HTMLLabelElement> {
  error?: boolean;
}

export const Label: React.FC<LabelProps> = ({
  className,
  error,
  children,
  ...props
}) => {
  return (
    <label
      className={cn(
        'text-sm font-medium text-[var(--text-secondary)] mb-1 block',
        error && 'text-red-500',
        className
      )}
      {...props}
    >
      {children}
    </label>
  );
};
