/**
 * Loading Skeleton Components
 *
 * PRD: Loading States - Create skeleton components for market cards, trader rows, etc.
 *
 * Provides reusable skeleton components for consistent loading states across the app.
 * Uses shimmer animation defined in globals.css for visual feedback.
 */

'use client';

import { cn } from '@/lib/utils';

/**
 * Base skeleton block with shimmer animation
 */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 animate-shimmer bg-[length:200%_100%] rounded',
        className
      )}
      {...props}
    />
  );
}

/**
 * Skeleton for market card (matches MarketCard component structure)
 */
export function MarketCardSkeleton() {
  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
      {/* Header image area */}
      <Skeleton className="h-32 rounded-none" />

      {/* Card content */}
      <div className="p-4 space-y-3">
        {/* Category badge */}
        <Skeleton className="h-5 w-16 rounded-full" />

        {/* Question - 2 lines */}
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>

        {/* Bid/Ask grid */}
        <div className="grid grid-cols-2 gap-2">
          <Skeleton className="h-12 rounded-md" />
          <Skeleton className="h-12 rounded-md" />
        </div>

        {/* Spread row */}
        <div className="flex justify-between">
          <Skeleton className="h-4 w-12" />
          <Skeleton className="h-4 w-16" />
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Skeleton className="h-3 w-12 mb-1" />
            <Skeleton className="h-4 w-16" />
          </div>
          <div>
            <Skeleton className="h-3 w-12 mb-1" />
            <Skeleton className="h-4 w-16" />
          </div>
        </div>

        {/* 24h change row */}
        <div className="flex justify-between">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-14" />
        </div>

        {/* Trade button */}
        <Skeleton className="h-10 w-full" />
      </div>
    </div>
  );
}

/**
 * Skeleton for table rows (generic, configurable columns)
 */
export function TableRowSkeleton({
  columns = 6,
  index = 0,
}: {
  columns?: number;
  index?: number;
}) {
  return (
    <div
      className="border-b border-gray-100 px-4 py-4 last:border-0"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <div className="flex items-center gap-4">
        {/* Avatar/icon column */}
        <Skeleton className="h-10 w-10" />

        {/* Main content column */}
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>

        {/* Additional columns */}
        {Array.from({ length: columns - 2 }).map((_, i) => (
          <Skeleton
            key={i}
            className="hidden sm:block h-4 w-16"
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Skeleton for market table view
 */
export function MarketTableSkeleton({ rows = 10 }: { rows?: number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="border-b border-gray-200 px-4 py-3 bg-gray-50">
        <div className="flex gap-4">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-16" />
        </div>
      </div>

      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <TableRowSkeleton key={i} index={i} columns={5} />
      ))}
    </div>
  );
}

/**
 * Skeleton for trader card (matches TraderCard component structure)
 */
export function TraderCardSkeleton() {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 animate-pulse">
      {/* Address skeleton */}
      <Skeleton className="h-5 w-32" />

      {/* Username skeleton */}
      <Skeleton className="mt-1 h-4 w-24" />

      {/* Score skeleton */}
      <div className="mt-4 flex items-baseline gap-2">
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-4 w-12" />
      </div>

      {/* Stats row skeleton */}
      <div className="mt-4 flex items-center justify-between">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-12" />
        <Skeleton className="h-4 w-14" />
      </div>
    </div>
  );
}

/**
 * Skeleton for tracked trader row
 */
export function TrackedTraderRowSkeleton({ index = 0 }: { index?: number }) {
  return (
    <div
      className="flex items-center gap-4 py-4 border-b border-gray-200 last:border-0"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Name/Address column */}
      <div className="flex-1 min-w-0">
        <Skeleton className="h-5 w-32 mb-1" />
        <Skeleton className="h-4 w-24" />
      </div>

      {/* Smart score badge */}
      <Skeleton className="h-6 w-12" />

      {/* PnL */}
      <div className="w-24 text-right">
        <Skeleton className="h-3 w-8 mb-1 ml-auto" />
        <Skeleton className="h-5 w-16 ml-auto" />
      </div>

      {/* Trades */}
      <div className="w-20 text-right">
        <Skeleton className="h-3 w-8 mb-1 ml-auto" />
        <Skeleton className="h-5 w-12 ml-auto" />
      </div>

      {/* Actions */}
      <Skeleton className="h-8 w-8 rounded" />
    </div>
  );
}

/**
 * Skeleton for activity feed row
 */
export function ActivityRowSkeleton({ index = 0 }: { index?: number }) {
  return (
    <div
      className="flex items-center gap-4 py-3 border-b border-gray-100 last:border-0"
      style={{ animationDelay: `${index * 30}ms` }}
    >
      {/* Timestamp */}
      <Skeleton className="h-4 w-28 shrink-0" />

      {/* Trader name */}
      <div className="w-28 shrink-0">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-3 w-16 mt-1" />
      </div>

      {/* Market question */}
      <div className="flex-1 min-w-0">
        <Skeleton className="h-4 w-full max-w-xs" />
      </div>

      {/* Side badge */}
      <Skeleton className="h-6 w-12 rounded-full shrink-0" />

      {/* Outcome */}
      <Skeleton className="h-4 w-12 shrink-0" />

      {/* Price */}
      <Skeleton className="h-4 w-12 shrink-0" />

      {/* Amount */}
      <Skeleton className="h-4 w-16 shrink-0" />
    </div>
  );
}

/**
 * Skeleton for watchlist item
 */
export function WatchlistItemSkeleton({ index = 0 }: { index?: number }) {
  return (
    <div
      className="flex items-center gap-4 py-4 border-b border-gray-200 last:border-0"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Market question */}
      <div className="flex-1 min-w-0">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-24 mt-1" />
      </div>

      {/* Price */}
      <Skeleton className="h-5 w-16" />

      {/* 24h change */}
      <Skeleton className="h-5 w-14" />

      {/* Actions */}
      <Skeleton className="h-8 w-8 rounded" />
    </div>
  );
}

/**
 * Skeleton for leaderboard row
 */
export function LeaderboardRowSkeleton({ index = 0 }: { index?: number }) {
  return (
    <div
      className="flex items-center gap-4 py-3 border-b border-gray-100 last:border-0"
      style={{ animationDelay: `${index * 30}ms` }}
    >
      {/* Rank */}
      <Skeleton className="h-6 w-8 rounded-full shrink-0" />

      {/* Trader info */}
      <div className="flex-1 min-w-0">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-24 mt-1" />
      </div>

      {/* PnL */}
      <Skeleton className="h-5 w-20 shrink-0" />

      {/* Win rate */}
      <Skeleton className="h-5 w-12 shrink-0" />

      {/* Trades */}
      <Skeleton className="h-5 w-16 shrink-0" />
    </div>
  );
}

/**
 * Generic list skeleton wrapper
 */
export function ListSkeleton({
  count = 5,
  children,
  className,
}: {
  count?: number;
  children: (index: number) => React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('divide-y divide-gray-200', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i}>{children(i)}</div>
      ))}
    </div>
  );
}

/**
 * Inline spinner for mutations/actions
 */
export function Spinner({
  size = 'md',
  className,
}: {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}) {
  const sizeClasses = {
    sm: 'h-4 w-4 border-2',
    md: 'h-6 w-6 border-2',
    lg: 'h-8 w-8 border-4',
  };

  return (
    <div
      className={cn(
        'animate-spin rounded-full border-gray-200 border-t-indigo-600',
        sizeClasses[size],
        className
      )}
    />
  );
}

/**
 * Loading overlay for components being refetched
 */
export function RefetchingOverlay({
  isRefetching,
  children,
}: {
  isRefetching: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="relative">
      {children}
      {isRefetching && (
        <div className="absolute inset-0 bg-white/60 flex items-center justify-center rounded-lg">
          <Spinner size="md" />
        </div>
      )}
    </div>
  );
}

/**
 * Stale data indicator badge
 */
export function StaleIndicator({
  isStale,
  isRefetching,
  className,
}: {
  isStale: boolean;
  isRefetching: boolean;
  className?: string;
}) {
  if (!isStale && !isRefetching) return null;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-xs',
        isRefetching ? 'text-indigo-600' : 'text-amber-600',
        className
      )}
    >
      {isRefetching ? (
        <>
          <Spinner size="sm" />
          <span>Updating...</span>
        </>
      ) : (
        <>
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          <span>Stale data</span>
        </>
      )}
    </span>
  );
}

/**
 * Button loading state wrapper
 */
export function LoadingButton({
  isLoading,
  disabled,
  children,
  loadingText,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  isLoading?: boolean;
  loadingText?: string;
}) {
  return (
    <button
      disabled={isLoading || disabled}
      className={cn(
        'relative inline-flex items-center justify-center gap-2',
        isLoading && 'cursor-not-allowed opacity-70',
        className
      )}
      {...props}
    >
      {isLoading && <Spinner size="sm" />}
      <span className={isLoading && loadingText ? '' : ''}>
        {isLoading && loadingText ? loadingText : children}
      </span>
    </button>
  );
}

export default {
  Skeleton,
  MarketCardSkeleton,
  MarketTableSkeleton,
  TraderCardSkeleton,
  TrackedTraderRowSkeleton,
  ActivityRowSkeleton,
  WatchlistItemSkeleton,
  LeaderboardRowSkeleton,
  ListSkeleton,
  Spinner,
  RefetchingOverlay,
  StaleIndicator,
  LoadingButton,
};
