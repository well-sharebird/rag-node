import React, { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { X } from 'lucide-react';

export interface ModalProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  showClose?: boolean;
  closeOnOverlay?: boolean;
  width?: string | number;
}

export const Modal: React.FC<ModalProps> = ({
  open = false,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
  showClose = true,
  closeOnOverlay = true,
  width,
}) => {
  // Close on Escape key
  useEffect(() => {
    if (!open) return;

    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onOpenChange?.(false);
      }
    };

    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="bird-modal-overlay" onClick={closeOnOverlay ? () => onOpenChange?.(false) : undefined}>
      <div
        className={cn('bird-modal', className)}
        style={{ maxWidth: width }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        {(title || showClose) && (
          <div className="bird-modal-header">
            <div className="flex items-center gap-3">
              {title && <h2 className="bird-modal-title">{title}</h2>}
            </div>
            {showClose && (
              <button
                className="bird-modal-close"
                onClick={() => onOpenChange?.(false)}
                aria-label="Close"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        )}

        {/* Description */}
        {description && (
          <div className="px-6 pb-4">
            <p className="text-sm text-gray-500">{description}</p>
          </div>
        )}

        {/* Body */}
        <div className="bird-modal-body">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="bird-modal-footer">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};
