/**
 * Chart Tooltip Component
 *
 * Sprint 04 - Data Visualization
 * PRD: chart_tooltip
 *
 * Features:
 * - Styled container with date/time and price display
 * - Price shown as both percentage and cents
 * - Price change from previous period with directional indicator
 * - Smart positioning to avoid chart edges
 *
 * Note: OHLC and volume data are not available from the Polymarket CLOB
 * timeseries API (which returns simple {t, p} points). If OHLC data becomes
 * available in the future, this component can be extended.
 */

'use client';

import * as React from 'react';
import { format } from 'date-fns';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Data point shape expected by the tooltip
 */
export interface ChartDataPoint {
  timestamp: number;
  price: number;
  formattedTime?: string;
  /** Price from the previous data point (for calculating change) */
  previousPrice?: number;
}

/**
 * Props for ChartTooltip component
 */
export interface ChartTooltipProps {
  /** Whether the tooltip is active/visible */
  active?: boolean;
  /** Recharts payload with data point */
  payload?: Array<{ value: number; payload: ChartDataPoint }>;
  /** Optional outcome name to display */
  outcomeName?: string;
  /** Optional CSS class */
  className?: string;
  /** Coordinates for edge detection (from Recharts) */
  coordinate?: { x: number; y: number };
  /** Chart dimensions for edge positioning */
  viewBox?: { x: number; y: number; width: number; height: number };
}

/**
 * Format price as percentage (0-100%)
 */
function formatPriceAsPercent(price: number): string {
  return `${(price * 100).toFixed(1)}%`;
}

/**
 * Format price as cents (0-100¢)
 */
function formatPriceAsCents(price: number): string {
  return `${Math.round(price * 100)}¢`;
}

/**
 * Calculate price change between two values
 */
function calculatePriceChange(
  currentPrice: number,
  previousPrice: number | undefined
): { absolute: number; percent: number } | null {
  if (previousPrice === undefined || previousPrice === 0) {
    return null;
  }

  const absolute = currentPrice - previousPrice;
  const percent = (absolute / previousPrice) * 100;

  return { absolute, percent };
}

/**
 * Get the change indicator icon and color
 */
function getChangeIndicator(change: number): {
  icon: typeof ArrowUp | typeof ArrowDown | typeof Minus;
  colorClass: string;
} {
  if (change > 0.0001) {
    return { icon: ArrowUp, colorClass: 'text-green-600' };
  } else if (change < -0.0001) {
    return { icon: ArrowDown, colorClass: 'text-red-600' };
  }
  return { icon: Minus, colorClass: 'text-gray-400' };
}

/**
 * ChartTooltip Component
 *
 * Enhanced tooltip for price charts showing:
 * - Date and time
 * - Current price as percentage and cents
 * - Price change from previous period (absolute and percentage)
 *
 * @example
 * ```tsx
 * <Tooltip
 *   content={<ChartTooltip outcomeName="Yes" />}
 *   cursor={{ stroke: '#6366f1' }}
 * />
 * ```
 */
export function ChartTooltip({
  active,
  payload,
  outcomeName,
  className,
  coordinate,
  viewBox,
}: ChartTooltipProps) {
  // Early return if not active or no data
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const data = payload[0];
  if (!data) {
    return null;
  }

  const point = data.payload;
  const currentPrice = data.value;
  const date = new Date(point.timestamp * 1000);

  // Calculate price change
  const priceChange = calculatePriceChange(currentPrice, point.previousPrice);
  const changeIndicator = priceChange ? getChangeIndicator(priceChange.absolute) : null;
  const ChangeIcon = changeIndicator?.icon;

  // Calculate position classes for edge avoidance
  // If near right edge, position tooltip to the left
  const positionClasses = React.useMemo(() => {
    if (!coordinate || !viewBox) {
      return '';
    }

    const rightEdgeThreshold = viewBox.width * 0.8;
    const topEdgeThreshold = viewBox.height * 0.2;

    let classes = '';

    // Near right edge - handled by Recharts, but we can add visual tweaks
    if (coordinate.x > rightEdgeThreshold) {
      classes += ' -translate-x-full';
    }

    // Near top - shift down
    if (coordinate.y < topEdgeThreshold) {
      classes += ' translate-y-4';
    }

    return classes;
  }, [coordinate, viewBox]);

  return (
    <div
      className={cn(
        'rounded-lg border border-gray-200 bg-white px-3 py-2.5 shadow-lg min-w-[160px]',
        positionClasses,
        className
      )}
      data-testid="chart-tooltip"
    >
      {/* Date and Time */}
      <div className="text-xs text-gray-500 mb-1.5">
        {format(date, 'MMM d, yyyy')}
        <span className="ml-1.5 text-gray-400">{format(date, 'HH:mm')}</span>
      </div>

      {/* Outcome Name and Current Price */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-center gap-1.5">
          {outcomeName && (
            <span className="text-sm text-gray-600">{outcomeName}</span>
          )}
        </div>
        <span className="text-lg font-semibold text-gray-900">
          {formatPriceAsPercent(currentPrice)}
        </span>
      </div>

      {/* Price in cents */}
      <div className="text-xs text-gray-400 text-right">
        {formatPriceAsCents(currentPrice)}
      </div>

      {/* Price Change from Previous Period */}
      {priceChange && ChangeIcon && (
        <div
          className={cn(
            'flex items-center justify-end gap-1 mt-1.5 pt-1.5 border-t border-gray-100',
            changeIndicator?.colorClass
          )}
          data-testid="price-change"
        >
          <ChangeIcon className="h-3 w-3" />
          <span className="text-xs font-medium">
            {priceChange.absolute > 0 ? '+' : ''}
            {(priceChange.absolute * 100).toFixed(2)}¢
          </span>
          <span className="text-xs text-gray-400">
            ({priceChange.percent > 0 ? '+' : ''}
            {priceChange.percent.toFixed(1)}%)
          </span>
        </div>
      )}
    </div>
  );
}

export default ChartTooltip;
