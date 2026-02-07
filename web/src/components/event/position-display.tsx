/**
 * Position Display Component
 *
 * Sprint 03 - Trading Panel UI
 * PRD: position_display
 *
 * Features:
 * - Shows user's current position in this market
 * - Displays: Shares held, Avg cost, Current value, PnL
 * - Color codes PnL (green positive, red negative)
 * - Placeholder 'Close Position' button
 * - Only shown when user has non-zero position
 */

'use client';

import { memo, useMemo } from 'react';
import { Wallet, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Position data for display
 */
export interface Position {
  /** Outcome ID for this position */
  outcomeId: string;
  /** Outcome name (e.g., "Yes", "No") */
  outcomeName: string;
  /** Number of shares held */
  quantity: number;
  /** Average cost basis per share (0.0 to 1.0) */
  avgCost: number;
  /** Current market price per share (0.0 to 1.0) */
  currentPrice: number;
  /** Unrealized profit/loss in USD */
  unrealizedPnl: number;
  /** Realized profit/loss in USD */
  realizedPnl: number;
}

export interface PositionDisplayProps {
  /** User's position in this market (null if no position) */
  position: Position | null;
  /** Called when user clicks "Close Position" button */
  onClosePosition?: () => void;
  /** Whether the component is in a loading state */
  loading?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Formats a number as USD currency
 */
function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Formats price as cents
 */
function formatPriceAsCents(price: number): string {
  const cents = Math.round(price * 100);
  return `${cents}¢`;
}

/**
 * Formats shares with appropriate precision
 */
function formatShares(shares: number): string {
  if (shares >= 1000) {
    return shares.toLocaleString('en-US', { maximumFractionDigits: 0 });
  }
  return shares.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * PositionDisplay - Shows user's current position in the market
 *
 * Only renders when user has a non-zero position
 */
export const PositionDisplay = memo(function PositionDisplay({
  position,
  onClosePosition,
  loading = false,
  className,
}: PositionDisplayProps) {
  // Calculate current value and total PnL
  const calculations = useMemo(() => {
    if (!position || position.quantity === 0) {
      return null;
    }

    // Current value = shares * current price
    const currentValue = position.quantity * position.currentPrice;
    // Cost basis = shares * avg cost
    const costBasis = position.quantity * position.avgCost;
    // Total PnL = unrealized + realized
    const totalPnl = position.unrealizedPnl + position.realizedPnl;

    return {
      currentValue,
      costBasis,
      totalPnl,
    };
  }, [position]);

  // Don't render if no position or zero quantity
  if (!position || position.quantity === 0) {
    return null;
  }

  // Loading skeleton
  if (loading) {
    return (
      <div
        className={cn(
          'rounded-lg border border-gray-200 bg-white p-4 space-y-3',
          className
        )}
        aria-busy="true"
        aria-label="Loading position"
        data-testid="position-display-loading"
      >
        <div className="animate-pulse space-y-3">
          <div className="flex items-center gap-2">
            <div className="h-5 w-5 bg-gray-200 rounded"></div>
            <div className="h-4 bg-gray-200 rounded w-24"></div>
          </div>
          <div className="space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="flex justify-between">
                <div className="h-3 bg-gray-200 rounded w-20"></div>
                <div className="h-3 bg-gray-200 rounded w-16"></div>
              </div>
            ))}
          </div>
          <div className="h-9 bg-gray-200 rounded w-full"></div>
        </div>
      </div>
    );
  }

  if (!calculations) {
    return null;
  }

  const { currentValue, totalPnl } = calculations;
  const isProfitable = totalPnl >= 0;
  const PnlIcon = isProfitable ? TrendingUp : TrendingDown;

  return (
    <div
      className={cn(
        'rounded-lg border bg-white p-4',
        isProfitable ? 'border-green-200' : 'border-red-200',
        className
      )}
      role="region"
      aria-label="Your position"
      data-testid="position-display"
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <Wallet className="h-4 w-4 text-gray-600" />
        <h3 className="text-sm font-medium text-gray-900">Your Position</h3>
        <span className="text-xs text-gray-500 ml-auto">
          {position.outcomeName}
        </span>
      </div>

      {/* Position details */}
      <div className="space-y-2 text-sm">
        {/* Shares held */}
        <PositionRow
          label="Shares"
          value={formatShares(position.quantity)}
        />

        {/* Average cost */}
        <PositionRow
          label="Avg Cost"
          value={formatPriceAsCents(position.avgCost)}
        />

        {/* Current value */}
        <PositionRow
          label="Value"
          value={formatCurrency(currentValue)}
        />

        {/* PnL */}
        <PositionRow
          label="P&L"
          value={
            <span
              className={cn(
                'inline-flex items-center gap-1 font-medium',
                isProfitable ? 'text-green-600' : 'text-red-600'
              )}
            >
              <PnlIcon className="h-3 w-3" />
              {isProfitable ? '+' : ''}
              {formatCurrency(totalPnl)}
            </span>
          }
        />
      </div>

      {/* Close position button (placeholder) */}
      <button
        type="button"
        onClick={onClosePosition}
        disabled={!onClosePosition}
        className={cn(
          'w-full mt-4 py-2 px-4 rounded-lg text-sm font-medium transition-colors',
          'border border-gray-300 text-gray-700',
          'hover:bg-gray-50 hover:border-gray-400',
          'focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2',
          'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:border-gray-300'
        )}
        aria-label="Close position"
        data-testid="close-position-button"
      >
        Close Position
      </button>
    </div>
  );
});

/**
 * Position row component for consistent layout
 */
interface PositionRowProps {
  label: string;
  value: React.ReactNode;
}

const PositionRow = memo(function PositionRow({
  label,
  value,
}: PositionRowProps) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-gray-600">{label}</span>
      <span className="text-gray-900">{value}</span>
    </div>
  );
});

export default PositionDisplay;
