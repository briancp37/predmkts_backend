/**
 * Trade Direction Toggle Component
 *
 * Sprint 03 - Trading Panel UI
 * PRD: trade_direction_toggle
 *
 * Features:
 * - Segmented control with Buy/Sell options
 * - Color coded: Buy=green, Sell=red
 * - Updates panel UI based on selected direction
 * - Stores direction in component state
 * - Keyboard shortcut hints (B for Buy, S for Sell)
 */

'use client';

import { useCallback, useEffect, memo } from 'react';
import { cn } from '@/lib/utils';

export type TradeDirection = 'buy' | 'sell';

export interface TradeDirectionToggleProps {
  /** Currently selected direction */
  direction: TradeDirection;
  /** Callback when direction changes */
  onDirectionChange: (direction: TradeDirection) => void;
  /** Whether the toggle is disabled */
  disabled?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * TradeDirectionToggle - Segmented control for Buy/Sell selection
 *
 * Displays two buttons in a segmented control style:
 * - Buy: Green accent color
 * - Sell: Red accent color
 *
 * Supports keyboard shortcuts (B for Buy, S for Sell) when any part
 * of the toggle is focused.
 */
export const TradeDirectionToggle = memo(function TradeDirectionToggle({
  direction,
  onDirectionChange,
  disabled = false,
  className,
}: TradeDirectionToggleProps) {
  // Handle keyboard shortcuts
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (disabled) return;

      const key = event.key.toLowerCase();

      if (key === 'b') {
        event.preventDefault();
        onDirectionChange('buy');
      } else if (key === 's') {
        event.preventDefault();
        onDirectionChange('sell');
      } else if (key === 'arrowleft' || key === 'arrowright') {
        event.preventDefault();
        onDirectionChange(direction === 'buy' ? 'sell' : 'buy');
      }
    },
    [direction, onDirectionChange, disabled]
  );

  // Global keyboard shortcuts (only when toggle or its children are focused)
  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      // Only respond if the toggle container or its children are focused
      const toggleContainer = document.getElementById('trade-direction-toggle');
      if (!toggleContainer?.contains(document.activeElement)) return;
      if (disabled) return;

      const key = event.key.toLowerCase();

      if (key === 'b') {
        event.preventDefault();
        onDirectionChange('buy');
      } else if (key === 's') {
        event.preventDefault();
        onDirectionChange('sell');
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [onDirectionChange, disabled]);

  return (
    <div className={cn('space-y-2', className)}>
      <label className="text-sm font-medium text-gray-700">
        Trade Direction
      </label>
      <div
        id="trade-direction-toggle"
        role="radiogroup"
        aria-label="Select trade direction"
        className={cn(
          'flex rounded-lg border border-gray-200 bg-gray-100 p-1',
          disabled && 'opacity-50'
        )}
        onKeyDown={handleKeyDown}
      >
        <DirectionButton
          direction="buy"
          isSelected={direction === 'buy'}
          onSelect={() => onDirectionChange('buy')}
          disabled={disabled}
          tabIndex={direction === 'buy' ? 0 : -1}
        />
        <DirectionButton
          direction="sell"
          isSelected={direction === 'sell'}
          onSelect={() => onDirectionChange('sell')}
          disabled={disabled}
          tabIndex={direction === 'sell' ? 0 : -1}
        />
      </div>
    </div>
  );
});

interface DirectionButtonProps {
  direction: TradeDirection;
  isSelected: boolean;
  onSelect: () => void;
  disabled?: boolean;
  tabIndex: number;
}

/**
 * Individual direction button with appropriate styling
 */
const DirectionButton = memo(function DirectionButton({
  direction,
  isSelected,
  onSelect,
  disabled = false,
  tabIndex,
}: DirectionButtonProps) {
  const isBuy = direction === 'buy';
  const label = isBuy ? 'Buy' : 'Sell';
  const shortcutKey = isBuy ? 'B' : 'S';

  return (
    <button
      type="button"
      role="radio"
      aria-checked={isSelected}
      tabIndex={tabIndex}
      onClick={disabled ? undefined : onSelect}
      disabled={disabled}
      className={cn(
        // Base styles
        'flex-1 flex items-center justify-center gap-1.5 py-2 px-4 rounded-md text-sm font-medium transition-all',
        // Focus styles
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
        isBuy
          ? 'focus-visible:ring-green-500'
          : 'focus-visible:ring-red-500',
        // Selected state
        isSelected && [
          isBuy
            ? 'bg-green-500 text-white shadow-sm'
            : 'bg-red-500 text-white shadow-sm',
        ],
        // Unselected state
        !isSelected && [
          'bg-transparent text-gray-600',
          !disabled && (isBuy
            ? 'hover:text-green-600 hover:bg-green-50'
            : 'hover:text-red-600 hover:bg-red-50'),
        ],
        // Disabled state
        disabled && 'cursor-not-allowed'
      )}
      aria-label={`${label} (${shortcutKey})`}
    >
      <span>{label}</span>
      <kbd
        className={cn(
          'hidden sm:inline-flex items-center justify-center w-5 h-5 text-xs rounded',
          isSelected
            ? isBuy
              ? 'bg-green-600 text-green-100'
              : 'bg-red-600 text-red-100'
            : 'bg-gray-200 text-gray-500'
        )}
        aria-hidden="true"
      >
        {shortcutKey}
      </kbd>
    </button>
  );
});

export default TradeDirectionToggle;
