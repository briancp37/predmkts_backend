/**
 * Trade Summary Component
 *
 * Sprint 03 - Trading Panel UI
 * PRD: trade_summary
 *
 * Features:
 * - Displays order details: Outcome, Direction, Amount, Shares, Avg Price
 * - Shows potential return with percentage
 * - Estimated fees line (placeholder)
 * - Total cost/proceeds calculation
 * - Real-time updates as inputs change
 */

'use client';

import { memo, useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { TradeDirection } from './trade-direction-toggle';

export interface TradeSummaryProps {
  /** Selected outcome name */
  outcomeName: string | null;
  /** Trade direction (buy/sell) */
  direction: TradeDirection;
  /** Trade amount in USD */
  amount: number | null;
  /** Price of the outcome (0.0 to 1.0) */
  price: number;
  /** Estimated fees (placeholder, default 0) */
  estimatedFees?: number;
  /** Whether the summary is in a loading state */
  loading?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Calculates the number of shares for a given amount and price
 */
function calculateShares(amount: number, price: number): number {
  if (price <= 0 || price >= 1) return 0;
  return amount / price;
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
 * Formats price as cents
 */
function formatPriceAsCents(price: number): string {
  const cents = Math.round(price * 100);
  return `${cents}¢`;
}

/**
 * Calculates potential return for a buy order
 * Each share pays out $1 if the outcome wins
 */
function calculatePotentialReturn(
  shares: number,
  amount: number,
  fees: number
): number {
  // Payout is shares * $1, minus the cost and fees
  const payout = shares;
  return payout - amount - fees;
}

/**
 * Calculates ROI percentage
 */
function calculateROI(potentialReturn: number, amount: number): number {
  if (amount <= 0) return 0;
  return (potentialReturn / amount) * 100;
}

/**
 * TradeSummary - Displays order summary before submission
 */
export const TradeSummary = memo(function TradeSummary({
  outcomeName,
  direction,
  amount,
  price,
  estimatedFees = 0,
  loading = false,
  className,
}: TradeSummaryProps) {
  // Calculate derived values
  const calculations = useMemo(() => {
    if (amount === null || amount <= 0 || price <= 0 || price >= 1) {
      return null;
    }

    const shares = calculateShares(amount, price);
    const potentialReturn = calculatePotentialReturn(shares, amount, estimatedFees);
    const roi = calculateROI(potentialReturn, amount);
    const totalCost = amount + estimatedFees;

    return {
      shares,
      avgPrice: price,
      potentialReturn,
      roi,
      totalCost,
    };
  }, [amount, price, estimatedFees]);

  // Determine if we have enough info to show the summary
  const isComplete = outcomeName !== null && calculations !== null;

  // Show placeholder when incomplete
  if (!isComplete) {
    return (
      <div
        className={cn(
          'rounded-lg border border-gray-200 bg-gray-50 p-4',
          className
        )}
        aria-label="Trade summary - incomplete"
      >
        <div className="text-center text-sm text-gray-500">
          {outcomeName === null
            ? 'Select an outcome to see order summary'
            : 'Enter an amount to see order summary'}
        </div>
      </div>
    );
  }

  // Loading skeleton
  if (loading) {
    return (
      <div
        className={cn('rounded-lg border border-gray-200 bg-white p-4 space-y-3', className)}
        aria-busy="true"
        aria-label="Loading trade summary"
      >
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-gray-200 rounded w-1/3"></div>
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex justify-between">
                <div className="h-3 bg-gray-200 rounded w-20"></div>
                <div className="h-3 bg-gray-200 rounded w-16"></div>
              </div>
            ))}
          </div>
          <div className="border-t border-gray-200 pt-2">
            <div className="flex justify-between">
              <div className="h-4 bg-gray-200 rounded w-24"></div>
              <div className="h-4 bg-gray-200 rounded w-20"></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const { shares, avgPrice, potentialReturn, roi, totalCost } = calculations;

  return (
    <div
      className={cn('rounded-lg border border-gray-200 bg-white p-4', className)}
      role="region"
      aria-label="Trade summary"
    >
      {/* Header */}
      <h3 className="text-sm font-medium text-gray-900 mb-3">Order Summary</h3>

      {/* Order details */}
      <div className="space-y-2 text-sm">
        {/* Outcome */}
        <SummaryRow label="Outcome" value={outcomeName} />

        {/* Direction */}
        <SummaryRow
          label="Direction"
          value={
            <span
              className={cn(
                'font-medium',
                direction === 'buy' ? 'text-green-600' : 'text-red-600'
              )}
            >
              {direction === 'buy' ? 'Buy' : 'Sell'}
            </span>
          }
        />

        {/* Amount */}
        <SummaryRow label="Amount" value={formatCurrency(amount!)} />

        {/* Shares */}
        <SummaryRow label="Shares" value={formatShares(shares)} />

        {/* Avg Price */}
        <SummaryRow label="Avg Price" value={formatPriceAsCents(avgPrice)} />
      </div>

      {/* Divider */}
      <div className="border-t border-gray-200 my-3" />

      {/* Potential return section */}
      <div className="space-y-2 text-sm">
        {/* Estimated fees */}
        <SummaryRow
          label="Est. Fees"
          value={
            estimatedFees > 0 ? (
              formatCurrency(estimatedFees)
            ) : (
              <span className="text-gray-400">$0.00</span>
            )
          }
          sublabel="(placeholder)"
        />

        {/* Total cost/proceeds */}
        <SummaryRow
          label={direction === 'buy' ? 'Total Cost' : 'Total Proceeds'}
          value={
            <span className="font-medium text-gray-900">
              {formatCurrency(totalCost)}
            </span>
          }
          highlight
        />
      </div>

      {/* Divider */}
      <div className="border-t border-gray-200 my-3" />

      {/* Potential return */}
      <div className="flex justify-between items-center">
        <span className="text-sm text-gray-600">Potential Return</span>
        <div className="text-right">
          <div
            className={cn(
              'text-sm font-semibold',
              potentialReturn >= 0 ? 'text-green-600' : 'text-red-600'
            )}
          >
            {potentialReturn >= 0 ? '+' : ''}
            {formatCurrency(potentialReturn)}
          </div>
          <div
            className={cn(
              'text-xs',
              roi >= 0 ? 'text-green-600' : 'text-red-600'
            )}
          >
            {roi >= 0 ? '+' : ''}
            {roi.toFixed(1)}%
          </div>
        </div>
      </div>
    </div>
  );
});

/**
 * Summary row component for consistent layout
 */
interface SummaryRowProps {
  label: string;
  value: React.ReactNode;
  sublabel?: string;
  highlight?: boolean;
}

const SummaryRow = memo(function SummaryRow({
  label,
  value,
  sublabel,
  highlight = false,
}: SummaryRowProps) {
  return (
    <div
      className={cn(
        'flex justify-between items-center',
        highlight && 'font-medium'
      )}
    >
      <span className="text-gray-600">
        {label}
        {sublabel && (
          <span className="text-xs text-gray-400 ml-1">{sublabel}</span>
        )}
      </span>
      <span className={cn('text-gray-900', highlight && 'font-medium')}>
        {value}
      </span>
    </div>
  );
});

export default TradeSummary;
