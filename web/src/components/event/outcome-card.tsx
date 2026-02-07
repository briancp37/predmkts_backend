/**
 * Outcome Card Components
 *
 * Sprint 02 - Market Display Components
 * PRD: outcome_cards
 *
 * Features:
 * - OutcomeCard: Individual outcome with probability, price, and 24h change
 * - OutcomeCardList: Renders all outcomes for a market
 * - Color-coded probability display (green for >50%, red for <50%)
 * - Hover state with subtle background change
 * - Clickable to select outcome for trading
 */

'use client';

import { memo, useCallback } from 'react';
import { cn } from '@/lib/utils';
import {
  formatProbability,
  formatProbabilityAsCents,
  getProbabilityColor,
  ProbabilityChange,
} from './probability-display';

// ============================================================================
// Types
// ============================================================================

export interface OutcomeCardData {
  /** Unique outcome identifier */
  id: string;
  /** CLOB token ID for this outcome */
  tokenId: string;
  /** Human-readable outcome name (e.g., "Yes", "No") */
  outcomeName: string;
  /** Current price (0.0 to 1.0) */
  currentPrice: number;
  /** Total volume traded on this outcome in USD */
  volume?: number;
  /** Price change in last 24 hours (absolute, e.g., 0.05 for 5 cents) */
  priceChange24h?: number;
}

// ============================================================================
// OutcomeCard Component
// ============================================================================

export interface OutcomeCardProps {
  /** Outcome data to display */
  outcome: OutcomeCardData;
  /** Whether this outcome is currently selected */
  isSelected?: boolean;
  /** Callback when the outcome card is clicked */
  onSelect?: (outcomeId: string) => void;
  /** Whether the card is clickable */
  clickable?: boolean;
  /** Size variant */
  size?: 'sm' | 'md';
  /** Additional CSS classes */
  className?: string;
}

/**
 * OutcomeCard - Displays a single outcome with price and 24h change
 *
 * Shows the outcome name, current price (as percentage and cents),
 * and 24h price change with color coding. Supports selection state
 * for trading integration.
 *
 * @example
 * ```tsx
 * <OutcomeCard
 *   outcome={{
 *     id: 'outcome-yes-123',
 *     tokenId: 'token123',
 *     outcomeName: 'Yes',
 *     currentPrice: 0.65,
 *     priceChange24h: 0.05,
 *   }}
 *   isSelected={selectedId === 'outcome-yes-123'}
 *   onSelect={(id) => setSelectedId(id)}
 * />
 * ```
 */
export const OutcomeCard = memo(function OutcomeCard({
  outcome,
  isSelected = false,
  onSelect,
  clickable = true,
  size = 'md',
  className,
}: OutcomeCardProps) {
  const colors = getProbabilityColor(outcome.currentPrice);

  const handleClick = useCallback(() => {
    if (clickable && onSelect) {
      onSelect(outcome.id);
    }
  }, [clickable, onSelect, outcome.id]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if ((event.key === 'Enter' || event.key === ' ') && clickable && onSelect) {
        event.preventDefault();
        onSelect(outcome.id);
      }
    },
    [clickable, onSelect, outcome.id]
  );

  const sizeClasses = {
    sm: {
      container: 'p-2',
      name: 'text-sm',
      price: 'text-base',
      cents: 'text-xs',
    },
    md: {
      container: 'p-3',
      name: 'text-base',
      price: 'text-lg',
      cents: 'text-sm',
    },
  };

  const classes = sizeClasses[size];

  return (
    <div
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        // Base styles
        'flex items-center justify-between rounded-lg border transition-all',
        classes.container,
        // Clickable styles
        clickable && [
          'cursor-pointer',
          'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
        ],
        // Selected state
        isSelected && [
          'border-indigo-500 bg-indigo-50',
          'ring-1 ring-indigo-500',
        ],
        // Unselected state
        !isSelected && [
          'border-gray-200 bg-gray-50',
          clickable && 'hover:border-gray-300 hover:bg-gray-100',
        ],
        className
      )}
      aria-pressed={clickable ? isSelected : undefined}
      aria-label={
        clickable
          ? `Select ${outcome.outcomeName} outcome at ${formatProbability(outcome.currentPrice)}`
          : undefined
      }
    >
      {/* Left side: Outcome name */}
      <span
        className={cn(
          'font-medium',
          classes.name,
          isSelected ? 'text-indigo-900' : 'text-gray-900'
        )}
      >
        {outcome.outcomeName}
      </span>

      {/* Right side: Price display and 24h change */}
      <div className="flex items-center gap-3">
        {/* 24h change */}
        {outcome.priceChange24h !== undefined && outcome.priceChange24h !== 0 && (
          <ProbabilityChange change={outcome.priceChange24h} size="sm" />
        )}

        {/* Price as percentage */}
        <span
          className={cn(
            'font-semibold px-2 py-0.5 rounded',
            classes.price,
            colors.bg,
            colors.text
          )}
        >
          {formatProbability(outcome.currentPrice)}
        </span>

        {/* Price as cents */}
        <span className={cn('text-gray-500 min-w-[3rem] text-right', classes.cents)}>
          {formatProbabilityAsCents(outcome.currentPrice)}
        </span>
      </div>
    </div>
  );
});

// ============================================================================
// OutcomeCardList Component
// ============================================================================

export interface OutcomeCardListProps {
  /** List of outcomes to display */
  outcomes: OutcomeCardData[];
  /** Currently selected outcome ID */
  selectedOutcomeId?: string | null;
  /** Callback when an outcome is selected */
  onOutcomeSelect?: (outcomeId: string) => void;
  /** Whether the cards are clickable */
  clickable?: boolean;
  /** Size variant for all cards */
  size?: 'sm' | 'md';
  /** Layout direction */
  layout?: 'vertical' | 'horizontal';
  /** Additional CSS classes */
  className?: string;
}

/**
 * OutcomeCardList - Renders a list of OutcomeCards
 *
 * Handles layout and selection state for multiple outcomes.
 * Supports both vertical (stacked) and horizontal (grid) layouts.
 *
 * @example
 * ```tsx
 * <OutcomeCardList
 *   outcomes={[
 *     { id: 'yes', tokenId: 't1', outcomeName: 'Yes', currentPrice: 0.65, priceChange24h: 0.05 },
 *     { id: 'no', tokenId: 't2', outcomeName: 'No', currentPrice: 0.35, priceChange24h: -0.05 },
 *   ]}
 *   selectedOutcomeId="yes"
 *   onOutcomeSelect={(id) => console.log('Selected:', id)}
 * />
 * ```
 */
export const OutcomeCardList = memo(function OutcomeCardList({
  outcomes,
  selectedOutcomeId,
  onOutcomeSelect,
  clickable = true,
  size = 'md',
  layout = 'vertical',
  className,
}: OutcomeCardListProps) {
  if (!outcomes || outcomes.length === 0) {
    return (
      <div className={cn('text-sm text-gray-500 text-center py-4', className)}>
        No outcomes available
      </div>
    );
  }

  return (
    <div
      className={cn(
        layout === 'vertical' ? 'space-y-2' : 'grid grid-cols-2 gap-2',
        className
      )}
    >
      {outcomes.map((outcome) => (
        <OutcomeCard
          key={outcome.id}
          outcome={outcome}
          isSelected={selectedOutcomeId === outcome.id}
          onSelect={onOutcomeSelect}
          clickable={clickable}
          size={size}
        />
      ))}
    </div>
  );
});

export default OutcomeCard;
