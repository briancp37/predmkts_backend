'use client';

import * as React from 'react';
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ChevronDown,
} from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Per-page options for the pagination
 */
export const PER_PAGE_OPTIONS = [10, 25, 50, 100, 200, 500, 1000] as const;
export type PerPageOption = (typeof PER_PAGE_OPTIONS)[number];

export interface MarketsPaginationProps {
  /** Current page (1-indexed) */
  page: number;
  /** Items per page */
  perPage: PerPageOption;
  /** Total number of items */
  total: number;
  /** Callback when page changes */
  onPageChange: (page: number) => void;
  /** Callback when per-page changes */
  onPerPageChange: (perPage: PerPageOption) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * MarketsPagination component with per-page selector and navigation
 *
 * PRD #11 - Create MarketsPagination component
 */
export function MarketsPagination({
  page,
  perPage,
  total,
  onPageChange,
  onPerPageChange,
  className,
}: MarketsPaginationProps) {
  const [isPerPageOpen, setIsPerPageOpen] = React.useState(false);
  const perPageRef = React.useRef<HTMLDivElement>(null);

  // Calculate pagination values
  const totalPages = Math.ceil(total / perPage);
  const startItem = total === 0 ? 0 : (page - 1) * perPage + 1;
  const endItem = Math.min(page * perPage, total);

  // Navigation state
  const isFirstPage = page <= 1;
  const isLastPage = page >= totalPages;

  // Handle outside click for per-page dropdown
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (perPageRef.current && !perPageRef.current.contains(event.target as Node)) {
        setIsPerPageOpen(false);
      }
    }
    if (isPerPageOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isPerPageOpen]);

  // Handle escape key for per-page dropdown
  React.useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsPerPageOpen(false);
      }
    }
    if (isPerPageOpen) {
      document.addEventListener('keydown', handleEscape);
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isPerPageOpen]);

  // Handle per-page change - reset to page 1
  const handlePerPageChange = (newPerPage: PerPageOption) => {
    onPerPageChange(newPerPage);
    onPageChange(1);
    setIsPerPageOpen(false);
  };

  // Navigation button component
  const NavButton = ({
    onClick,
    disabled,
    children,
    label,
  }: {
    onClick: () => void;
    disabled: boolean;
    children: React.ReactNode;
    label: string;
  }) => (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        'flex items-center justify-center rounded-md p-2 transition-colors',
        disabled
          ? 'cursor-not-allowed text-gray-300'
          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
      )}
    >
      {children}
    </button>
  );

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-between gap-4 sm:flex-row',
        className
      )}
    >
      {/* Showing X-Y of Z markets */}
      <div className="text-sm text-gray-600">
        {total === 0 ? (
          'No markets to display'
        ) : (
          <>
            Showing <span className="font-medium">{startItem}</span>-
            <span className="font-medium">{endItem}</span> of{' '}
            <span className="font-medium">{total.toLocaleString()}</span> markets
          </>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Per-page selector */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">Per page:</span>
          <div ref={perPageRef} className="relative">
            <button
              type="button"
              onClick={() => setIsPerPageOpen(!isPerPageOpen)}
              className={cn(
                'flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50'
              )}
              aria-expanded={isPerPageOpen}
              aria-haspopup="listbox"
            >
              {perPage}
              <ChevronDown
                className={cn(
                  'h-4 w-4 text-gray-500 transition-transform',
                  isPerPageOpen && 'rotate-180'
                )}
              />
            </button>

            {isPerPageOpen && (
              <div
                className="absolute bottom-full right-0 z-20 mb-1 min-w-24 rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
                role="listbox"
              >
                {PER_PAGE_OPTIONS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => handlePerPageChange(option)}
                    className={cn(
                      'w-full px-4 py-2 text-left text-sm transition-colors',
                      perPage === option
                        ? 'bg-indigo-50 text-indigo-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-50'
                    )}
                    role="option"
                    aria-selected={perPage === option}
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Navigation controls */}
        <div className="flex items-center gap-1 rounded-lg border border-gray-200 bg-white p-1">
          {/* First */}
          <NavButton
            onClick={() => onPageChange(1)}
            disabled={isFirstPage}
            label="First page"
          >
            <ChevronsLeft className="h-4 w-4" />
          </NavButton>

          {/* Previous */}
          <NavButton
            onClick={() => onPageChange(page - 1)}
            disabled={isFirstPage}
            label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </NavButton>

          {/* Page X of Y */}
          <span className="px-3 text-sm text-gray-700">
            Page <span className="font-medium">{page}</span> of{' '}
            <span className="font-medium">{totalPages || 1}</span>
          </span>

          {/* Next */}
          <NavButton
            onClick={() => onPageChange(page + 1)}
            disabled={isLastPage}
            label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </NavButton>

          {/* Last */}
          <NavButton
            onClick={() => onPageChange(totalPages)}
            disabled={isLastPage}
            label="Last page"
          >
            <ChevronsRight className="h-4 w-4" />
          </NavButton>
        </div>
      </div>
    </div>
  );
}

export default MarketsPagination;
