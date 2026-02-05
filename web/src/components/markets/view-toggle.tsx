'use client';

import { LayoutGrid, List } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * View mode options
 */
export type ViewMode = 'card' | 'table';

export interface ViewToggleProps {
  /** Current view mode */
  value: ViewMode;
  /** Callback when view mode changes */
  onChange: (mode: ViewMode) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * ViewToggle component for switching between card and table views
 *
 * PRD #11 - Create ViewToggle component
 */
export function ViewToggle({ value, onChange, className }: ViewToggleProps) {
  return (
    <div
      className={cn(
        'inline-flex rounded-lg border border-gray-200 bg-white p-1',
        className
      )}
      role="group"
      aria-label="View mode"
    >
      <button
        type="button"
        onClick={() => onChange('card')}
        className={cn(
          'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
          value === 'card'
            ? 'bg-indigo-100 text-indigo-700'
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
        )}
        aria-pressed={value === 'card'}
        aria-label="Card view"
      >
        <LayoutGrid className="h-4 w-4" />
        <span className="hidden sm:inline">Cards</span>
      </button>
      <button
        type="button"
        onClick={() => onChange('table')}
        className={cn(
          'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
          value === 'table'
            ? 'bg-indigo-100 text-indigo-700'
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
        )}
        aria-pressed={value === 'table'}
        aria-label="Table view"
      >
        <List className="h-4 w-4" />
        <span className="hidden sm:inline">Table</span>
      </button>
    </div>
  );
}

export default ViewToggle;
