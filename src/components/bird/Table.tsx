import React from 'react';
import { cn } from '@/lib/utils';

// Table Root
export interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  striped?: boolean;
  hover?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export const Table = React.forwardRef<HTMLTableElement, TableProps>(
  ({ className, striped = false, hover = true, size = 'md', ...props }, ref) => {
    return (
      <div className="bird-table-container">
        <table
          ref={ref}
          className={cn(
            'bird-table',
            striped && 'bird-table-striped',
            hover && '',
            className
          )}
          {...props}
        />
      </div>
    );
  }
);

Table.displayName = 'Table';

// Table Header
export interface TableHeaderProps extends React.HTMLAttributes<HTMLTableSectionElement> {
  children: React.ReactNode;
}

export const TableHeader = React.forwardRef<HTMLTableSectionElement, TableHeaderProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <thead ref={ref} className={className} {...props}>
        {children}
      </thead>
    );
  }
);

TableHeader.displayName = 'TableHeader';

// Table Body
export interface TableBodyProps extends React.HTMLAttributes<HTMLTableSectionElement> {
  children: React.ReactNode;
}

export const TableBody = React.forwardRef<HTMLTableSectionElement, TableBodyProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <tbody ref={ref} className={className} {...props}>
        {children}
      </tbody>
    );
  }
);

TableBody.displayName = 'TableBody';

// Table Row
export interface TableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  onClick?: () => void;
}

export const TableRow = React.forwardRef<HTMLTableRowElement, TableRowProps>(
  ({ className, onClick, ...props }, ref) => {
    return (
      <tr
        ref={ref}
        className={cn(onClick && 'cursor-pointer', className)}
        onClick={onClick}
        {...props}
      />
    );
  }
);

TableRow.displayName = 'TableRow';

// Table Cell
export interface TableCellProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  variant?: 'default' | 'header';
}

export const TableCell = React.forwardRef<HTMLTableCellElement, TableCellProps>(
  ({ className, variant = 'default', children, ...props }, ref) => {
    const Tag = variant === 'header' ? 'th' : 'td';
    return (
      <Tag ref={ref} className={cn(className)} {...props}>
        {children}
      </Tag>
    );
  }
);

TableCell.displayName = 'TableCell';

// Table Caption
export const TableCaption: React.FC<React.HTMLAttributes<HTMLTableCaptionElement>> = ({
  className,
  children,
  ...props
}) => {
  return (
    <caption className={cn('py-3 text-sm text-gray-500', className)} {...props}>
      {children}
    </caption>
  );
};
