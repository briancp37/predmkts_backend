/**
 * Outcome Selector Component
 *
 * Sprint 03 - Trading Panel UI
 * PRD: outcome_selector
 *
 * Features:
 * - Radio-button style selection of outcomes
 * - Displays all outcomes with prices (Yes 12c, No 88c)
 * - Highlights selected outcome with accent color
 * - Shows real-time price for each outcome
 * - Supports keyboard navigation between outcomes
 * - Emits selected outcome ID on change
 */

'use client';

import { useCallback, useRef, memo } from 'react';
import { cn } from '@/lib/utils';
import { formatProbabilityAsCents, getProbabilityColor } from './probability-display';

export interface Outcome {
  /** Unique outcome identifier */
  id: string;
  /** CLOB token ID for this outcome */
  tokenId: string;
  /** Human-readable outcome name (e.g., "Yes", "No") */
  outcomeName: string;
  /** Current price (0.0 to 1.0) */
  currentPrice: number;
}

export interface OutcomeSelectorProps {
  /** List of outcomes to display */
  outcomes: Outcome[];
  /** Currently selected outcome ID */
  selectedOutcomeId: string | null;
  /** Callback when an outcome is selected */
  onOutcomeSelect: (outcomeId: string) => void;
  /** Whether the selector is disabled */
  disabled?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * OutcomeSelector - Radio-button style outcome selection for trading panel
 *
 * Displays outcomes with prices and allows selection via click or keyboard.
 * The selected outcome is highlighted with an accent color border and background.
 */
export const OutcomeSelector = memo(function OutcomeSelector({
  outcomes,
  selectedOutcomeId,
  onOutcomeSelect,
  disabled = false,
  className,
}: OutcomeSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent, currentIndex: number) => {
      if (disabled) return;

      let nextIndex: number | null = null;

      switch (event.key) {
        case 'ArrowDown':
        case 'ArrowRight':
          event.preventDefault();
          nextIndex = (currentIndex + 1) % outcomes.length;
          break;
        case 'ArrowUp':
        case 'ArrowLeft':
          event.preventDefault();
          nextIndex = (currentIndex - 1 + outcomes.length) % outcomes.length;
          break;
        case 'Home':
          event.preventDefault();
          nextIndex = 0;
          break;
        case 'End':
          event.preventDefault();
          nextIndex = outcomes.length - 1;
          break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          if (outcomes[currentIndex]) {
            onOutcomeSelect(outcomes[currentIndex].id);
          }
          return;
      }

      if (nextIndex !== null) {
        // Focus the next outcome button
        const buttons = containerRef.current?.querySelectorAll('[role="radio"]');
        if (buttons && buttons[nextIndex]) {
          (buttons[nextIndex] as HTMLElement).focus();
        }
      }
    },
    [outcomes, onOutcomeSelect, disabled]
  );

  if (!outcomes || outcomes.length === 0) {
    return (
      <div className={cn('text-sm text-gray-500 text-center py-4', className)}>
        No outcomes available
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      role="radiogroup"
      aria-label="Select an outcome"
      className={cn('space-y-2', className)}
    >
      <label className="text-sm font-medium text-gray-700">
        Select Outcome
      </label>
      <div className="space-y-2">
        {outcomes.map((outcome, index) => (
          <OutcomeOption
            key={outcome.id}
            outcome={outcome}
            isSelected={selectedOutcomeId === outcome.id}
            onSelect={() => onOutcomeSelect(outcome.id)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            disabled={disabled}
            tabIndex={selectedOutcomeId === outcome.id || (!selectedOutcomeId && index === 0) ? 0 : -1}
          />
        ))}
      </div>
    </div>
  );
});

interface OutcomeOptionProps {
  outcome: Outcome;
  isSelected: boolean;
  onSelect: () => void;
  onKeyDown: (event: React.KeyboardEvent) => void;
  disabled?: boolean;
  tabIndex: number;
}

/**
 * Individual outcome option with radio-button styling
 */
const OutcomeOption = memo(function OutcomeOption({
  outcome,
  isSelected,
  onSelect,
  onKeyDown,
  disabled = false,
  tabIndex,
}: OutcomeOptionProps) {
  const colors = getProbabilityColor(outcome.currentPrice);

  return (
    <button
      type="button"
      role="radio"
      aria-checked={isSelected}
      tabIndex={tabIndex}
      onClick={disabled ? undefined : onSelect}
      onKeyDown={onKeyDown}
      disabled={disabled}
      className={cn(
        // Base styles
        'w-full flex items-center justify-between p-3 rounded-lg border-2 transition-all',
        // Focus styles
        'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
        // Selected state
        isSelected && [
          'border-indigo-500 bg-indigo-50',
          'ring-1 ring-indigo-500',
        ],
        // Unselected state
        !isSelected && [
          'border-gray-200 bg-white',
          'hover:border-gray-300 hover:bg-gray-50',
        ],
        // Disabled state
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <div className="flex items-center gap-3">
        {/* Radio indicator */}
        <div
          className={cn(
            'h-4 w-4 rounded-full border-2 flex items-center justify-center transition-colors',
            isSelected ? 'border-indigo-500 bg-indigo-500' : 'border-gray-300 bg-white'
          )}
        >
          {isSelected && (
            <div className="h-1.5 w-1.5 rounded-full bg-white" />
          )}
        </div>

        {/* Outcome name */}
        <span className={cn(
          'font-medium',
          isSelected ? 'text-indigo-900' : 'text-gray-900'
        )}>
          {outcome.outcomeName}
        </span>
      </div>

      {/* Price display */}
      <span
        className={cn(
          'text-lg font-semibold px-2 py-0.5 rounded',
          colors.bg,
          colors.text
        )}
      >
        {formatProbabilityAsCents(outcome.currentPrice)}
      </span>
    </button>
  );
});

export default OutcomeSelector;
