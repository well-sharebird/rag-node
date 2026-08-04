import React from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'prefix' | 'suffix'> {
  error?: string;
  helperText?: string;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, helperText, prefix, suffix, type = 'text', disabled, ...props }, ref) => {
    return (
      <div className="w-full">
        <div className={cn(
          'relative flex items-center',
          prefix && 'pl-2',
          suffix && 'pr-2'
        )}>
          {prefix && (
            <span className="flex items-center text-gray-400 mr-2">
              {prefix}
            </span>
          )}
          <input
            ref={ref}
            type={type}
            className={cn(
              'enterprise-input',
              prefix && 'pl-2',
              suffix && 'pr-2',
              error && 'enterprise-input-error',
              disabled && 'opacity-50',
              className
            )}
            disabled={disabled}
            {...props}
          />
          {suffix && (
            <span className="flex items-center text-gray-400 ml-2">
              {suffix}
            </span>
          )}
        </div>
        {error && (
          <p className="mt-1.5 text-xs text-red-500">{error}</p>
        )}
        {helperText && !error && (
          <p className="mt-1.5 text-xs text-gray-400">{helperText}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
