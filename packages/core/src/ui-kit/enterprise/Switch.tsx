import React from 'react';
import { cn } from '@/lib/utils';

export interface SwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  size?: 'sm' | 'md';
  disabled?: boolean;
}

export const Switch: React.FC<SwitchProps> = ({
  className,
  checked = false,
  onCheckedChange,
  size = 'md',
  disabled = false,
  ...props
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onCheckedChange?.(e.target.checked);
  };

  return (
    <input
      type="checkbox"
      role="switch"
      checked={checked}
      onChange={handleChange}
      disabled={disabled}
      className={cn(
        'enterprise-switch appearance-none inline-flex items-center cursor-pointer transition-colors duration-200',
        'bg-[var(--gray-300)] rounded-full',
        'focus:outline-none focus:ring-2 focus:ring-[var(--primary-light)] focus:ring-offset-1',
        checked && 'bg-[var(--primary)]',
        disabled && 'opacity-50 cursor-not-allowed',
        size === 'sm' && 'w-8 h-4',
        size === 'md' && 'w-9 h-5',
        className
      )}
      {...props}
    />
  );
};
