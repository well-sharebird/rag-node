import React from 'react';
import { cn } from '@/lib/utils';

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options?: Array<{ value: string; label: string }>;
  placeholder?: string;
}

export const Select: React.FC<SelectProps> = ({
  className,
  options = [],
  placeholder,
  children,
  ...props
}) => {
  return (
    <select
      className={cn(
        'enterprise-select',
        className
      )}
      {...props}
    >
      {placeholder && (
        <option value="" disabled>{placeholder}</option>
      )}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
      {children}
    </select>
  );
};
