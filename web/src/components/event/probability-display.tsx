/**
 * Probability Display Components
 *
 * Reusable components for displaying probability values throughout the event detail page.
 * - ProbabilityBadge: Inline badge for probability display
 * - ProbabilityBar: Visual bar representation with color gradient
 * - Helper functions for formatting and color calculation
 */

'use client';

import { memo, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * Format a probability value (0.0-1.0) as a percentage string.
 * @param value - Probability value between 0 and 1
 * @param decimals - Number of decimal places (default 0)
 * @returns Formatted string like "12%" or "12.5%"
 */
export function formatProbability(value: number, decimals = 0): string {
  const percent = value * 100;
  return `${percent.toFixed(decimals)}%`;
}

/**
 * Format a probability value as a price in cents.
 * @param value - Probability value between 0 and 1
 * @returns Formatted string like "12¢"
 */
export function formatProbabilityAsCents(value: number): string {
  const cents = Math.round(value * 100);
  return `${cents}¢`;
}

/**
 * Get the appropriate color class based on probability value.
 * Higher probability = green, lower = red, middle = orange/yellow.
 * @param value - Probability value between 0 and 1
 * @returns Object with background and text color classes
 */
export function getProbabilityColor(value: number): {
  bg: string;
  text: string;
  barColor: string;
} {
  if (value >= 0.7) {
    return {
      bg: 'bg-green-50',
      text: 'text-green-700',
      barColor: 'bg-green-500',
    };
  }
  if (value >= 0.5) {
    return {
      bg: 'bg-emerald-50',
      text: 'text-emerald-700',
      barColor: 'bg-emerald-500',
    };
  }
  if (value >= 0.3) {
    return {
      bg: 'bg-yellow-50',
      text: 'text-yellow-700',
      barColor: 'bg-yellow-500',
    };
  }
  if (value >= 0.15) {
    return {
      bg: 'bg-orange-50',
      text: 'text-orange-700',
      barColor: 'bg-orange-500',
    };
  }
  return {
    bg: 'bg-red-50',
    text: 'text-red-700',
    barColor: 'bg-red-500',
  };
}

// ============================================================================
// ProbabilityBadge Component
// ============================================================================

export interface ProbabilityBadgeProps {
  /** Probability value between 0 and 1 */
  value: number;
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';
  /** Show as cents (12¢) instead of percent (12%) */
  showAsCents?: boolean;
  /** Number of decimal places for percentage */
  decimals?: number;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Inline badge component for displaying probability values.
 * Automatically color-coded based on probability (green for high, red for low).
 */
export const ProbabilityBadge = memo(function ProbabilityBadge({
  value,
  size = 'md',
  showAsCents = false,
  decimals = 0,
  className,
}: ProbabilityBadgeProps) {
  const colors = getProbabilityColor(value);

  const sizeClasses = {
    sm: 'px-1.5 py-0.5 text-xs',
    md: 'px-2 py-0.5 text-sm',
    lg: 'px-3 py-1 text-base font-medium',
  };

  const displayValue = showAsCents
    ? formatProbabilityAsCents(value)
    : formatProbability(value, decimals);

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium',
        sizeClasses[size],
        colors.bg,
        colors.text,
        className
      )}
    >
      {displayValue}
    </span>
  );
});

// ============================================================================
// ProbabilityBar Component
// ============================================================================

export interface ProbabilityBarProps {
  /** Probability value between 0 and 1 */
  value: number;
  /** Height of the bar */
  height?: 'xs' | 'sm' | 'md' | 'lg';
  /** Show label inside or outside the bar */
  showLabel?: boolean;
  /** Label position when shown */
  labelPosition?: 'inside' | 'right';
  /** Animate the bar width on mount/change */
  animated?: boolean;
  /** Additional CSS classes for the container */
  className?: string;
}

/**
 * Visual bar representation of probability with color gradient.
 * The bar width represents the probability value.
 */
export const ProbabilityBar = memo(function ProbabilityBar({
  value,
  height = 'md',
  showLabel = false,
  labelPosition = 'right',
  animated = true,
  className,
}: ProbabilityBarProps) {
  const colors = getProbabilityColor(value);
  const [displayWidth, setDisplayWidth] = useState(animated ? 0 : value * 100);

  // Animate the bar width on mount or when value changes
  useEffect(() => {
    if (animated) {
      // Small delay to ensure the animation is visible
      const timer = setTimeout(() => {
        setDisplayWidth(value * 100);
      }, 50);
      return () => clearTimeout(timer);
    } else {
      setDisplayWidth(value * 100);
    }
  }, [value, animated]);

  const heightClasses = {
    xs: 'h-1',
    sm: 'h-2',
    md: 'h-3',
    lg: 'h-4',
  };

  const labelSizeClasses = {
    xs: 'text-xs',
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-sm font-medium',
  };

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div
        className={cn(
          'relative flex-1 overflow-hidden rounded-full bg-gray-100',
          heightClasses[height]
        )}
      >
        <div
          className={cn(
            'absolute inset-y-0 left-0 rounded-full',
            colors.barColor,
            animated && 'transition-all duration-500 ease-out'
          )}
          style={{ width: `${displayWidth}%` }}
        />
        {showLabel && labelPosition === 'inside' && height !== 'xs' && height !== 'sm' && (
          <span
            className={cn(
              'absolute inset-0 flex items-center justify-center text-white',
              labelSizeClasses[height]
            )}
          >
            {formatProbability(value)}
          </span>
        )}
      </div>
      {showLabel && labelPosition === 'right' && (
        <span className={cn('min-w-[3rem] text-right', colors.text, labelSizeClasses[height])}>
          {formatProbability(value)}
        </span>
      )}
    </div>
  );
});

// ============================================================================
// LargeProbabilityDisplay Component
// ============================================================================

export interface LargeProbabilityDisplayProps {
  /** Probability value between 0 and 1 */
  value: number;
  /** Optional label (e.g., "Yes", "No", outcome name) */
  label?: string;
  /** Show "chance" suffix after percentage */
  showChanceSuffix?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Large probability display for prominent placement (e.g., event header).
 * Shows probability as a large percentage with optional label.
 */
export const LargeProbabilityDisplay = memo(function LargeProbabilityDisplay({
  value,
  label,
  showChanceSuffix = false,
  className,
}: LargeProbabilityDisplayProps) {
  const colors = getProbabilityColor(value);

  return (
    <div className={cn('flex flex-col', className)}>
      {label && <span className="text-sm text-gray-500">{label}</span>}
      <div className="flex items-baseline gap-1">
        <span className={cn('text-3xl font-bold', colors.text)}>
          {formatProbability(value)}
        </span>
        {showChanceSuffix && <span className="text-lg text-gray-500">chance</span>}
      </div>
    </div>
  );
});

// ============================================================================
// ProbabilityChange Component
// ============================================================================

export interface ProbabilityChangeProps {
  /** Change value (can be positive or negative, in absolute terms like 0.05 for 5%) */
  change: number;
  /** Size variant */
  size?: 'sm' | 'md';
  /** Additional CSS classes */
  className?: string;
}

/**
 * Display probability change with up/down arrow and color coding.
 * Positive changes are green, negative are red.
 */
export const ProbabilityChange = memo(function ProbabilityChange({
  change,
  size = 'md',
  className,
}: ProbabilityChangeProps) {
  if (change === 0) {
    return (
      <span className={cn('text-gray-500', size === 'sm' ? 'text-xs' : 'text-sm', className)}>
        0%
      </span>
    );
  }

  const isPositive = change > 0;
  const arrow = isPositive ? '↑' : '↓';
  const colorClass = isPositive ? 'text-green-600' : 'text-red-600';
  const absChange = Math.abs(change * 100);

  return (
    <span
      className={cn('inline-flex items-center gap-0.5 font-medium', colorClass, size === 'sm' ? 'text-xs' : 'text-sm', className)}
    >
      <span>{arrow}</span>
      <span>{absChange.toFixed(1)}%</span>
    </span>
  );
});
