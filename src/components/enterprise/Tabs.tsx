import React, { useState } from 'react';
import { cn } from '@/lib/utils';

export interface TabsProps {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  className?: string;
  children: React.ReactNode;
}

export const Tabs: React.FC<TabsProps> = ({
  value,
  defaultValue,
  onValueChange,
  className,
  children,
}) => {
  const [internalValue, setInternalValue] = useState(defaultValue || '');
  const selectedValue = value !== undefined ? value : internalValue;

  const handleValueChange = (newValue: string) => {
    if (onValueChange) {
      onValueChange(newValue);
    } else {
      setInternalValue(newValue);
    }
  };

  return (
    <TabsContext.Provider value={{ value: selectedValue, onValueChange: handleValueChange }}>
      <div className={cn('w-full', className)}>
        {children}
      </div>
    </TabsContext.Provider>
  );
};

export interface TabsListProps {
  className?: string;
  children: React.ReactNode;
}

export const TabsList: React.FC<TabsListProps> = ({ className, children }) => {
  return (
    <div className={cn('flex gap-2 p-1 bg-[var(--gray-100)] rounded-lg', className)}>
      {children}
    </div>
  );
};

export interface TabsTriggerProps {
  value: string;
  className?: string;
  children: React.ReactNode;
  onClick?: () => void;
}

export const TabsTrigger: React.FC<TabsTriggerProps> = ({
  value,
  className,
  children,
  onClick,
}) => {
  const tabsContext = React.useContext(TabsContext);
  const isSelected = tabsContext?.value === value;

  const handleClick = () => {
    if (tabsContext?.onValueChange) {
      tabsContext.onValueChange(value);
    }
    onClick?.();
  };

  return (
    <button
      className={cn(
        'px-4 py-2 text-sm font-medium rounded-md transition-colors',
        isSelected
          ? 'bg-[var(--gray-0)] text-[var(--text-primary)] shadow-sm'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
        className
      )}
      onClick={handleClick}
      type="button"
    >
      {children}
    </button>
  );
};

export interface TabsContentProps {
  value: string;
  className?: string;
  children: React.ReactNode;
}

export const TabsContent: React.FC<TabsContentProps> = ({
  value,
  className,
  children,
}) => {
  const tabsContext = React.useContext(TabsContext);
  if (tabsContext?.value !== value) {
    return null;
  }

  return (
    <div className={cn('mt-4', className)}>
      {children}
    </div>
  );
};

const TabsContext = React.createContext<{ value: string; onValueChange?: (value: string) => void } | null>(null);
