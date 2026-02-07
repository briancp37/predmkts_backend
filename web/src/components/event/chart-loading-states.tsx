/**
 * Chart Loading States
 *
 * Sprint 04 - Data Visualization
 * PRD: chart_loading_states
 *
 * Features:
 * - ChartLoadingSkeleton with animated placeholder
 * - ChartEmpty for 'No data available' state
 * - ChartError with retry button
 * - ChartRefetchIndicator for subtle loading on range change
 * - All states maintain chart dimensions to prevent layout shift
 */

'use client';

import * as React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Props for ChartLoadingSkeleton
 */
export interface ChartLoadingSkeletonProps {
  /** Height in pixels (maintains chart dimensions during loading) */
  height: number;
  /** Additional CSS classes */
  className?: string;
  /** Loading message to display */
  message?: string;
}

/**
 * ChartLoadingSkeleton - Full skeleton for initial chart loading
 *
 * Displays an animated placeholder that maintains the chart's dimensions
 * to prevent layout shift. Used for initial data load (no cache).
 *
 * @example
 * ```tsx
 * if (isLoading) {
 *   return <ChartLoadingSkeleton height={300} />;
 * }
 * ```
 */
export function ChartLoadingSkeleton({
  height,
  className,
  message = 'Loading chart...',
}: ChartLoadingSkeletonProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-center bg-gray-50 rounded-lg animate-pulse',
        className
      )}
      style={{ height }}
      data-testid="chart-loading-skeleton"
    >
      <div className="flex flex-col items-center gap-2">
        <div className="h-8 w-8 rounded-full border-2 border-indigo-200 border-t-indigo-600 animate-spin" />
        <span className="text-sm text-gray-400">{message}</span>
      </div>
    </div>
  );
}

/**
 * Props for ChartEmpty
 */
export interface ChartEmptyProps {
  /** Height in pixels (maintains chart dimensions) */
  height: number;
  /** Message to display */
  message?: string;
  /** Additional CSS classes */
  className?: string;
}

/**
 * ChartEmpty - Empty state when no data is available
 *
 * Displays a centered message when the chart has no data to show.
 * Maintains chart dimensions to prevent layout shift.
 *
 * @example
 * ```tsx
 * if (!data || data.length === 0) {
 *   return <ChartEmpty height={300} message="No price data available" />;
 * }
 * ```
 */
export function ChartEmpty({
  height,
  message = 'No price data available',
  className,
}: ChartEmptyProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-center bg-gray-50 rounded-lg text-gray-500',
        className
      )}
      style={{ height }}
      data-testid="chart-empty"
    >
      {message}
    </div>
  );
}

/**
 * Props for ChartError
 */
export interface ChartErrorProps {
  /** Height in pixels (maintains chart dimensions) */
  height: number;
  /** Error message to display */
  error: string;
  /** Callback when retry button is clicked */
  onRetry?: () => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * ChartError - Error state with retry option
 *
 * Displays an error message and optional retry button when chart data fails to load.
 * Maintains chart dimensions to prevent layout shift.
 *
 * @example
 * ```tsx
 * if (error) {
 *   return (
 *     <ChartError
 *       height={300}
 *       error={error.message}
 *       onRetry={() => refetch()}
 *     />
 *   );
 * }
 * ```
 */
export function ChartError({
  height,
  error,
  onRetry,
  className,
}: ChartErrorProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center bg-gray-50 rounded-lg text-gray-500 gap-2',
        className
      )}
      style={{ height }}
      data-testid="chart-error"
    >
      <span className="text-sm">{error}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs text-indigo-600 hover:text-indigo-700 underline focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 rounded"
        >
          Retry
        </button>
      )}
    </div>
  );
}

/**
 * Props for ChartRefetchIndicator
 */
export interface ChartRefetchIndicatorProps {
  /** Whether data is currently being refetched */
  isRefetching: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * ChartRefetchIndicator - Subtle loading indicator for data refetch
 *
 * Displays a small, non-intrusive loading indicator when chart data is being
 * refetched (e.g., on time range change). Unlike the full skeleton, this
 * overlay allows the existing chart to remain visible.
 *
 * Position this component absolutely within a relative container that wraps
 * the chart.
 *
 * @example
 * ```tsx
 * <div className="relative">
 *   <ChartRefetchIndicator isRefetching={isFetching && !isLoading} />
 *   <PriceChart tokenId={tokenId} interval={interval} />
 * </div>
 * ```
 */
export function ChartRefetchIndicator({
  isRefetching,
  className,
}: ChartRefetchIndicatorProps) {
  if (!isRefetching) {
    return null;
  }

  return (
    <div
      className={cn(
        'absolute top-2 right-2 flex items-center gap-1.5 bg-white/90 backdrop-blur-sm rounded-full px-2 py-1 shadow-sm border border-gray-200 z-10',
        className
      )}
      data-testid="chart-refetch-indicator"
    >
      <Loader2 className="h-3 w-3 animate-spin text-indigo-600" />
      <span className="text-xs text-gray-600">Updating...</span>
    </div>
  );
}

/**
 * Props for ChartContainer
 */
export interface ChartContainerProps {
  /** Chart height in pixels */
  height: number;
  /** Whether to show refetch indicator */
  isRefetching?: boolean;
  /** Chart content */
  children: React.ReactNode;
  /** Additional CSS classes */
  className?: string;
}

/**
 * ChartContainer - Wrapper that handles refetch indicator positioning
 *
 * A convenience component that wraps chart content with proper positioning
 * for the refetch indicator overlay.
 *
 * @example
 * ```tsx
 * <ChartContainer height={300} isRefetching={isFetching && !isLoading}>
 *   <ResponsiveContainer>
 *     <AreaChart data={chartData}>...</AreaChart>
 *   </ResponsiveContainer>
 * </ChartContainer>
 * ```
 */
export function ChartContainer({
  height,
  isRefetching = false,
  children,
  className,
}: ChartContainerProps) {
  return (
    <div
      className={cn('relative w-full', className)}
      style={{ height }}
      data-testid="chart-container"
    >
      <ChartRefetchIndicator isRefetching={isRefetching} />
      {children}
    </div>
  );
}

export default {
  ChartLoadingSkeleton,
  ChartEmpty,
  ChartError,
  ChartRefetchIndicator,
  ChartContainer,
};
