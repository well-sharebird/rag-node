import { InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export interface SliderProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}

export function Slider({ className, error, ...props }: SliderProps) {
  return (
    <input
      type="range"
      className={cn(
        'w-full h-2 rounded-lg appearance-none cursor-pointer',
        'bg-gray-200',
        'accent-blue-500',
        'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
        error ? 'accent-red-500' : '',
        className
      )}
      {...props}
    />
  );
}
