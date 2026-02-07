/**
 * Trade Amount Input Component
 *
 * Sprint 03 - Trading Panel UI
 * PRD: amount_input
 *
 * Features:
 * - Numeric input with USD prefix indicator
 * - Quick-select buttons ($10, $50, $100, $500)
 * - Input validation (min $1, max based on liquidity)
 * - Shares calculation: amount / price = shares
 * - Potential payout display: shares * $1 (for winning outcome)
 * - ROI percentage: (payout - amount) / amount * 100
 */

'use client';

import { useCallback, useState, useEffect, memo, useRef } from 'react';
import { cn } from '@/lib/utils';

const QUICK_AMOUNTS = [10, 50, 100, 500] as const;
const MIN_AMOUNT = 1;
const DEFAULT_MAX_AMOUNT = 10000;

export interface TradeAmountInputProps {
  /** Current amount value */
  amount: number | null;
  /** Callback when amount changes */
  onAmountChange: (amount: number | null) => void;
  /** Price of the selected outcome (0.0 to 1.0) */
  price: number;
  /** Maximum allowed amount (based on liquidity) */
  maxAmount?: number;
  /** Whether the input is disabled */
  disabled?: boolean;
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
 * Calculates the potential payout if outcome wins
 * (Each share pays out $1 if the outcome wins)
 */
function calculatePayout(shares: number): number {
  return shares;
}

/**
 * Calculates ROI percentage
 */
function calculateROI(amount: number, payout: number): number {
  if (amount <= 0) return 0;
  return ((payout - amount) / amount) * 100;
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
 * TradeAmountInput - Numeric input for trade amount with calculations
 */
export const TradeAmountInput = memo(function TradeAmountInput({
  amount,
  onAmountChange,
  price,
  maxAmount = DEFAULT_MAX_AMOUNT,
  disabled = false,
  className,
}: TradeAmountInputProps) {
  const [inputValue, setInputValue] = useState<string>(
    amount !== null ? amount.toString() : ''
  );
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync input value with amount prop when it changes externally
  useEffect(() => {
    if (amount === null) {
      setInputValue('');
    } else if (parseFloat(inputValue) !== amount) {
      setInputValue(amount.toString());
    }
  }, [amount]);

  // Validate and update amount
  const validateAndUpdate = useCallback(
    (value: string) => {
      setInputValue(value);

      // Allow empty input
      if (value === '' || value === '.') {
        setError(null);
        onAmountChange(null);
        return;
      }

      const numValue = parseFloat(value);

      // Check for valid number
      if (isNaN(numValue)) {
        setError('Enter a valid amount');
        onAmountChange(null);
        return;
      }

      // Check minimum
      if (numValue < MIN_AMOUNT) {
        setError(`Minimum amount is ${formatCurrency(MIN_AMOUNT)}`);
        onAmountChange(null);
        return;
      }

      // Check maximum
      if (numValue > maxAmount) {
        setError(`Maximum amount is ${formatCurrency(maxAmount)}`);
        onAmountChange(null);
        return;
      }

      // Valid amount
      setError(null);
      onAmountChange(numValue);
    },
    [maxAmount, onAmountChange]
  );

  // Handle input change
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;

      // Only allow numbers and decimal point
      if (value !== '' && !/^\d*\.?\d*$/.test(value)) {
        return;
      }

      validateAndUpdate(value);
    },
    [validateAndUpdate]
  );

  // Handle quick amount button click
  const handleQuickAmount = useCallback(
    (quickAmount: number) => {
      if (disabled) return;
      setInputValue(quickAmount.toString());
      setError(null);
      onAmountChange(quickAmount);
      // Focus the input after selecting a quick amount
      inputRef.current?.focus();
    },
    [disabled, onAmountChange]
  );

  // Calculate derived values
  const validAmount = amount !== null && amount >= MIN_AMOUNT ? amount : 0;
  const shares = calculateShares(validAmount, price);
  const payout = calculatePayout(shares);
  const roi = calculateROI(validAmount, payout);

  // Determine if calculations should be shown
  const showCalculations = validAmount > 0 && price > 0 && price < 1;

  return (
    <div className={cn('space-y-3', className)}>
      <label className="text-sm font-medium text-gray-700">
        Amount
      </label>

      {/* Input with USD prefix */}
      <div className="relative">
        <span
          className={cn(
            'absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 font-medium',
            disabled && 'text-gray-400'
          )}
          aria-hidden="true"
        >
          $
        </span>
        <input
          ref={inputRef}
          type="text"
          inputMode="decimal"
          placeholder="0.00"
          value={inputValue}
          onChange={handleInputChange}
          disabled={disabled}
          aria-label="Trade amount in USD"
          aria-invalid={error !== null}
          aria-describedby={error ? 'amount-error' : undefined}
          className={cn(
            'w-full pl-7 pr-4 py-3 rounded-lg border text-lg font-medium',
            'focus:outline-none focus:ring-2 focus:ring-offset-1',
            error
              ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
              : 'border-gray-200 focus:ring-indigo-500 focus:border-indigo-500',
            disabled && 'bg-gray-100 cursor-not-allowed opacity-50'
          )}
        />
      </div>

      {/* Error message */}
      {error && (
        <p id="amount-error" className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}

      {/* Quick amount buttons */}
      <div className="flex gap-2">
        {QUICK_AMOUNTS.map((quickAmount) => (
          <QuickAmountButton
            key={quickAmount}
            amount={quickAmount}
            isSelected={amount === quickAmount}
            onClick={() => handleQuickAmount(quickAmount)}
            disabled={disabled || quickAmount > maxAmount}
          />
        ))}
      </div>

      {/* Calculations display */}
      {showCalculations && (
        <div className="rounded-lg bg-gray-50 p-3 space-y-2">
          {/* Shares calculation */}
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">Shares</span>
            <span className="font-medium text-gray-900">
              {formatShares(shares)}
            </span>
          </div>

          {/* Potential payout */}
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">Potential payout</span>
            <span className="font-medium text-gray-900">
              {formatCurrency(payout)}
            </span>
          </div>

          {/* ROI */}
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">Potential return</span>
            <span
              className={cn(
                'font-medium',
                roi > 0 ? 'text-green-600' : 'text-gray-900'
              )}
            >
              {roi > 0 ? '+' : ''}
              {roi.toFixed(1)}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
});

interface QuickAmountButtonProps {
  amount: number;
  isSelected: boolean;
  onClick: () => void;
  disabled?: boolean;
}

/**
 * Quick amount selection button
 */
const QuickAmountButton = memo(function QuickAmountButton({
  amount,
  isSelected,
  onClick,
  disabled = false,
}: QuickAmountButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all',
        'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
        isSelected && !disabled
          ? 'bg-indigo-100 text-indigo-700 border-2 border-indigo-500'
          : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50 hover:border-gray-300',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
      aria-pressed={isSelected}
    >
      ${amount}
    </button>
  );
});

export default TradeAmountInput;
