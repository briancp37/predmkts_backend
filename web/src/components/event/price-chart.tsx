/**
 * Price Chart Component
 *
 * Sprint 04 - Data Visualization
 * PRD: price_chart_component
 *
 * Features:
 * - Line chart with area fill using Recharts
 * - Uses useTimeseries hook for data fetching
 * - Y-axis formatted as percentage (0-100%)
 * - X-axis with time formatting
 * - Crosshair tooltip with exact price/time
 * - Gradient area fill under the line
 */

'use client';

import * as React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { format, isToday, isThisWeek, isThisYear } from 'date-fns';
import { useTimeseries, type TimeseriesInterval, type PricePoint } from '@/hooks';
import { cn } from '@/lib/utils';

export interface PriceChartProps {
  /** Token ID to fetch timeseries data for */
  tokenId: string | undefined | null;
  /** Time interval for data points (default: '1d') */
  interval?: TimeseriesInterval;
  /** Chart height in pixels (default: 300) */
  height?: number;
  /** Additional CSS classes */
  className?: string;
  /** Primary line color (default: indigo-500) */
  lineColor?: string;
  /** Whether to show the 50% reference line */
  showMidLine?: boolean;
  /** Outcome name for tooltip display */
  outcomeName?: string;
}

/**
 * Format timestamp for X-axis display based on time range
 */
function formatXAxis(timestamp: number, interval: TimeseriesInterval): string {
  const date = new Date(timestamp * 1000);

  switch (interval) {
    case '1m':
    case '5m':
    case '15m':
      // Short intervals: show time only (HH:mm)
      return format(date, 'HH:mm');
    case '1h':
    case '6h':
      // Medium intervals: show day and time if recent
      if (isToday(date)) {
        return format(date, 'HH:mm');
      }
      return format(date, 'MMM d HH:mm');
    case '1d':
      // Daily: show month and day
      if (isThisWeek(date)) {
        return format(date, 'EEE');
      }
      return format(date, 'MMM d');
    case '1w':
      // Weekly: show month and day
      return format(date, 'MMM d');
    case 'max':
      // Max: show month and year if older
      if (isThisYear(date)) {
        return format(date, 'MMM d');
      }
      return format(date, "MMM ''yy");
    default:
      return format(date, 'MMM d');
  }
}

/**
 * Format price as percentage (0-100%)
 */
function formatPrice(price: number): string {
  return `${(price * 100).toFixed(1)}%`;
}

/**
 * Format price for Y-axis tick (shorter format)
 */
function formatYAxisTick(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/**
 * Custom tooltip component for the price chart
 */
interface TooltipPayloadItem {
  value: number;
  payload: ChartDataPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  outcomeName?: string;
}

function CustomTooltip({ active, payload, outcomeName }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const data = payload[0];
  if (!data) {
    return null;
  }

  const point = data.payload;
  const date = new Date(point.timestamp * 1000);

  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-lg">
      <div className="text-xs text-gray-500 mb-1">
        {format(date, 'MMM d, yyyy HH:mm')}
      </div>
      <div className="flex items-center gap-2">
        {outcomeName && (
          <span className="text-sm text-gray-600">{outcomeName}:</span>
        )}
        <span className="text-base font-semibold text-gray-900">
          {formatPrice(data.value)}
        </span>
      </div>
      <div className="text-xs text-gray-400 mt-0.5">
        {Math.round(data.value * 100)}¢
      </div>
    </div>
  );
}

/**
 * Chart data point with timestamp
 */
interface ChartDataPoint {
  timestamp: number;
  price: number;
  formattedTime: string;
}

/**
 * Transform API response to chart data format
 */
function transformData(
  history: PricePoint[],
  interval: TimeseriesInterval
): ChartDataPoint[] {
  return history.map((point) => ({
    timestamp: point.timestamp,
    price: point.price,
    formattedTime: formatXAxis(point.timestamp, interval),
  }));
}

/**
 * Loading skeleton for the price chart
 */
function PriceChartSkeleton({ height }: { height: number }) {
  return (
    <div
      className="flex items-center justify-center bg-gray-50 rounded-lg animate-pulse"
      style={{ height }}
      data-testid="price-chart-loading"
    >
      <div className="flex flex-col items-center gap-2">
        <div className="h-8 w-8 rounded-full border-2 border-indigo-200 border-t-indigo-600 animate-spin" />
        <span className="text-sm text-gray-400">Loading chart...</span>
      </div>
    </div>
  );
}

/**
 * Empty state when no data is available
 */
function PriceChartEmpty({ height, message }: { height: number; message?: string }) {
  return (
    <div
      className="flex items-center justify-center bg-gray-50 rounded-lg text-gray-500"
      style={{ height }}
      data-testid="price-chart-empty"
    >
      {message || 'No price data available'}
    </div>
  );
}

/**
 * Error state with retry option
 */
function PriceChartError({
  height,
  error,
  onRetry,
}: {
  height: number;
  error: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center bg-gray-50 rounded-lg text-gray-500 gap-2"
      style={{ height }}
      data-testid="price-chart-error"
    >
      <span className="text-sm">{error}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs text-indigo-600 hover:text-indigo-700 underline"
        >
          Retry
        </button>
      )}
    </div>
  );
}

/**
 * PriceChart Component
 *
 * Displays an interactive price chart for a prediction market outcome.
 * Uses the useTimeseries hook to fetch price history data from the proxy API.
 *
 * @example
 * ```tsx
 * // Basic usage with token ID
 * <PriceChart tokenId="71321045679252212594626385532706912750332728571942532289631379312455583286595" />
 *
 * // With custom interval and styling
 * <PriceChart
 *   tokenId={outcome.tokenId}
 *   interval="1h"
 *   height={400}
 *   outcomeName="Yes"
 *   showMidLine
 * />
 * ```
 */
export function PriceChart({
  tokenId,
  interval = '1d',
  height = 300,
  className,
  lineColor = '#6366f1',
  showMidLine = true,
  outcomeName,
}: PriceChartProps) {
  const {
    data: timeseriesData,
    isLoading,
    error,
    refetch,
  } = useTimeseries(tokenId, { interval, enabled: !!tokenId });

  // Early return for missing token ID
  if (!tokenId) {
    return <PriceChartEmpty height={height} message="Select an outcome to view price history" />;
  }

  // Loading state
  if (isLoading) {
    return <PriceChartSkeleton height={height} />;
  }

  // Error state
  if (error) {
    return (
      <PriceChartError
        height={height}
        error={error instanceof Error ? error.message : 'Failed to load chart data'}
        onRetry={() => refetch()}
      />
    );
  }

  // Empty data state
  if (!timeseriesData?.history || timeseriesData.history.length === 0) {
    return <PriceChartEmpty height={height} />;
  }

  const chartData = transformData(timeseriesData.history, interval);

  // Calculate min/max for Y-axis domain with some padding
  const prices = chartData.map((d) => d.price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const padding = (maxPrice - minPrice) * 0.1;
  const yMin = Math.max(0, minPrice - padding);
  const yMax = Math.min(1, maxPrice + padding);

  // Create gradient ID unique to this chart instance
  const gradientId = React.useId();

  return (
    <div
      className={cn('w-full', className)}
      style={{ height }}
      data-testid="price-chart"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={lineColor} stopOpacity={0.3} />
              <stop offset="95%" stopColor={lineColor} stopOpacity={0.05} />
            </linearGradient>
          </defs>

          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#e5e7eb"
            vertical={false}
          />

          <XAxis
            dataKey="formattedTime"
            tick={{ fill: '#6b7280', fontSize: 11 }}
            tickLine={{ stroke: '#e5e7eb' }}
            axisLine={{ stroke: '#e5e7eb' }}
            dy={5}
            interval="preserveStartEnd"
            minTickGap={40}
          />

          <YAxis
            domain={[yMin, yMax]}
            tick={{ fill: '#6b7280', fontSize: 11 }}
            tickLine={{ stroke: '#e5e7eb' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickFormatter={formatYAxisTick}
            width={45}
            dx={-5}
          />

          {showMidLine && (
            <ReferenceLine
              y={0.5}
              stroke="#9ca3af"
              strokeDasharray="4 4"
              strokeWidth={1}
            />
          )}

          <Tooltip
            content={<CustomTooltip outcomeName={outcomeName} />}
            cursor={{
              stroke: '#6366f1',
              strokeWidth: 1,
              strokeDasharray: '4 4',
            }}
          />

          <Area
            type="monotone"
            dataKey="price"
            stroke={lineColor}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            dot={false}
            activeDot={{
              r: 4,
              fill: lineColor,
              stroke: '#fff',
              strokeWidth: 2,
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PriceChart;
