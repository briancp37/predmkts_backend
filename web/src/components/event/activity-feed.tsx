/**
 * Activity Feed Component
 *
 * Sprint 05 - Activity and Social
 * PRD: activity_feed, activity_item, activity_loading, polling_updates
 *
 * Features:
 * - Display recent trades for a market using useMarketTrades hook
 * - Trade items showing wallet, side (buy/sell), size, price, time
 * - Color coding: green for buy, red for sell
 * - Loading skeleton during fetch
 * - Empty state when no trades
 * - Load more button for additional trades
 * - Auto-polling every 30s with pause when tab is hidden
 * - "New activity" banner when new trades arrive
 * - Manual refresh button
 */

'use client';

import * as React from 'react';
import { ArrowUp, ArrowDown, RefreshCw, AlertCircle, Bell } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useMarketTrades, Trade } from '@/hooks/use-polymarket-proxy';

// =============================================================================
// Constants
// =============================================================================

/** Polling interval for activity feed (30 seconds) */
const POLLING_INTERVAL_MS = 30 * 1000;

// =============================================================================
// Custom Hooks
// =============================================================================

/**
 * Hook to detect document visibility state
 * Returns false when tab is hidden, true when visible
 */
function useDocumentVisibility(): boolean {
  const [isVisible, setIsVisible] = React.useState(() => {
    // SSR-safe: default to true, will be updated on mount
    if (typeof document === 'undefined') return true;
    return !document.hidden;
  });

  React.useEffect(() => {
    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  return isVisible;
}

// =============================================================================
// Types
// =============================================================================

export interface ActivityFeedProps {
  /** Condition ID for fetching market-specific trades */
  conditionId: string;
  /** Maximum number of trades to display initially */
  initialLimit?: number;
  /** Optional className for the container */
  className?: string;
  /** Enable auto-polling for updates (default: true) */
  enablePolling?: boolean;
  /** Polling interval in milliseconds (default: 30000) */
  pollingInterval?: number;
}

export interface ActivityItemProps {
  /** Trade data */
  trade: Trade;
  /** Optional className */
  className?: string;
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Format a timestamp as relative time (e.g., "2 min ago")
 */
function formatRelativeTime(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;

  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) {
    return days === 1 ? '1 day ago' : `${days} days ago`;
  }
  if (hours > 0) {
    return hours === 1 ? '1 hour ago' : `${hours} hours ago`;
  }
  if (minutes > 0) {
    return minutes === 1 ? '1 min ago' : `${minutes} min ago`;
  }
  if (seconds > 10) {
    return `${seconds} sec ago`;
  }
  return 'Just now';
}

/**
 * Truncate wallet address for display (e.g., "0x1234...5678")
 */
function truncateAddress(address: string): string {
  if (!address || address.length < 10) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

/**
 * Format trade size in dollars
 */
function formatDollarValue(price: string, size: string): string {
  const priceNum = parseFloat(price);
  const sizeNum = parseFloat(size);
  const value = priceNum * sizeNum;

  if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}k`;
  }
  if (value >= 1) {
    return `$${value.toFixed(2)}`;
  }
  return `$${value.toFixed(4)}`;
}

/**
 * Format share count
 */
function formatShares(size: string): string {
  const sizeNum = parseFloat(size);
  if (sizeNum >= 1000000) {
    return `${(sizeNum / 1000000).toFixed(1)}M`;
  }
  if (sizeNum >= 1000) {
    return `${(sizeNum / 1000).toFixed(1)}k`;
  }
  if (sizeNum >= 1) {
    return sizeNum.toFixed(0);
  }
  return sizeNum.toFixed(2);
}

/**
 * Format price as cents
 */
function formatPrice(price: string): string {
  const priceNum = parseFloat(price);
  return `${(priceNum * 100).toFixed(1)}¢`;
}

// =============================================================================
// Activity Item Component
// =============================================================================

/**
 * ActivityItem - Single trade display
 */
export function ActivityItem({ trade, className }: ActivityItemProps) {
  const isBuy = trade.side === 'BUY';
  const address = trade.makerAddress || 'Unknown';

  return (
    <div
      className={cn(
        'flex items-center gap-3 py-3 px-2 rounded-lg',
        'hover:bg-gray-50 transition-colors duration-150',
        className
      )}
    >
      {/* Side indicator icon */}
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          isBuy ? 'bg-green-100' : 'bg-red-100'
        )}
      >
        {isBuy ? (
          <ArrowUp className="h-4 w-4 text-green-600" />
        ) : (
          <ArrowDown className="h-4 w-4 text-red-600" />
        )}
      </div>

      {/* Trade details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {/* Wallet address */}
          <span className="font-mono text-sm text-gray-700 truncate">
            {truncateAddress(address)}
          </span>
          {/* Action */}
          <span
            className={cn(
              'text-sm font-medium',
              isBuy ? 'text-green-600' : 'text-red-600'
            )}
          >
            {isBuy ? 'bought' : 'sold'}
          </span>
        </div>
        {/* Size and price */}
        <div className="text-sm text-gray-500">
          {formatShares(trade.size)} shares @ {formatPrice(trade.price)}
          {trade.outcome && (
            <span className="ml-1 text-gray-400">
              ({trade.outcome})
            </span>
          )}
        </div>
      </div>

      {/* Dollar value and time */}
      <div className="flex-shrink-0 text-right">
        <div
          className={cn(
            'text-sm font-semibold',
            isBuy ? 'text-green-600' : 'text-red-600'
          )}
        >
          {formatDollarValue(trade.price, trade.size)}
        </div>
        <div className="text-xs text-gray-400">
          {formatRelativeTime(trade.timestamp)}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Loading Skeleton
// =============================================================================

/**
 * ActivitySkeleton - Animated loading placeholder
 */
export function ActivitySkeleton() {
  return (
    <div className="space-y-1">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 py-3 px-2 animate-pulse"
        >
          {/* Avatar skeleton */}
          <div className="w-8 h-8 rounded-full bg-gray-200" />

          {/* Text skeletons */}
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-gray-200 rounded w-3/4" />
            <div className="h-3 bg-gray-200 rounded w-1/2" />
          </div>

          {/* Value skeleton */}
          <div className="space-y-1">
            <div className="h-4 bg-gray-200 rounded w-12 ml-auto" />
            <div className="h-3 bg-gray-200 rounded w-16 ml-auto" />
          </div>
        </div>
      ))}
    </div>
  );
}

// =============================================================================
// Empty State
// =============================================================================

interface EmptyStateProps {
  message?: string;
}

function EmptyState({ message = 'No recent activity' }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-4">
        <RefreshCw className="h-6 w-6 text-gray-400" />
      </div>
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );
}

// =============================================================================
// Error State
// =============================================================================

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

function ErrorState({ message = 'Failed to load activity', onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mb-4">
        <AlertCircle className="h-6 w-6 text-red-400" />
      </div>
      <p className="text-sm text-gray-700 mb-4">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      )}
    </div>
  );
}

// =============================================================================
// New Activity Banner
// =============================================================================

interface NewActivityBannerProps {
  count: number;
  onClick: () => void;
}

/**
 * NewActivityBanner - Shows when new trades have arrived since last view
 */
function NewActivityBanner({ count, onClick }: NewActivityBannerProps) {
  if (count <= 0) return null;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full flex items-center justify-center gap-2 py-2 px-4',
        'bg-blue-50 text-blue-600 text-sm font-medium',
        'hover:bg-blue-100 transition-colors',
        'rounded-lg mb-2 animate-pulse'
      )}
    >
      <Bell className="h-4 w-4" />
      {count === 1 ? '1 new trade' : `${count} new trades`}
      <span className="text-blue-500">- Click to view</span>
    </button>
  );
}

// =============================================================================
// Activity Feed Component
// =============================================================================

/**
 * ActivityFeed - Recent trades activity feed
 *
 * Supports auto-polling with visibility detection to pause when tab is hidden.
 */
export function ActivityFeed({
  conditionId,
  initialLimit = 20,
  className,
  enablePolling = true,
  pollingInterval = POLLING_INTERVAL_MS,
}: ActivityFeedProps) {
  const [limit, setLimit] = React.useState(initialLimit);

  // Track seen trade IDs to detect new trades
  const [seenTradeIds, setSeenTradeIds] = React.useState<Set<string>>(new Set());
  const [newTradeCount, setNewTradeCount] = React.useState(0);
  const [showNewTrades, setShowNewTrades] = React.useState(true);

  // Pause polling when tab is hidden
  const isVisible = useDocumentVisibility();
  const shouldPoll = enablePolling && isVisible;

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    dataUpdatedAt,
  } = useMarketTrades(conditionId, {
    limit,
    refetchInterval: shouldPoll ? pollingInterval : false,
  });

  const trades = data?.trades ?? [];
  const hasMore = data?.hasMore ?? false;

  // Track new trades that appear after initial load
  React.useEffect(() => {
    if (!trades.length) return;

    const currentTradeIds = new Set(trades.map((t) => t.id));

    // On first load, just record all IDs as seen
    if (seenTradeIds.size === 0) {
      setSeenTradeIds(currentTradeIds);
      return;
    }

    // Count trades we haven't seen before
    const newTrades = trades.filter((t) => !seenTradeIds.has(t.id));

    if (newTrades.length > 0 && !showNewTrades) {
      // Only show banner if user hasn't dismissed it
      setNewTradeCount(newTrades.length);
    }
  }, [trades, seenTradeIds, showNewTrades]);

  // Handle clicking the "new activity" banner
  const handleViewNewTrades = () => {
    // Mark all current trades as seen
    setSeenTradeIds(new Set(trades.map((t) => t.id)));
    setNewTradeCount(0);
    setShowNewTrades(true);
  };

  // Handle load more
  const handleLoadMore = () => {
    setLimit((prev) => prev + 20);
  };

  // Handle manual refresh
  const handleRefresh = () => {
    refetch();
    // After manual refresh, show all trades and mark as seen
    setShowNewTrades(true);
    setNewTradeCount(0);
    // We'll update seenTradeIds when the new data arrives
  };

  // When manually refreshing, update seen IDs with new data
  React.useEffect(() => {
    if (showNewTrades && trades.length > 0) {
      setSeenTradeIds(new Set(trades.map((t) => t.id)));
    }
  }, [dataUpdatedAt, showNewTrades, trades]);

  // Loading state
  if (isLoading && trades.length === 0) {
    return (
      <div className={className}>
        <ActivitySkeleton />
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className={className}>
        <ErrorState
          message={error instanceof Error ? error.message : 'Failed to load activity'}
          onRetry={handleRefresh}
        />
      </div>
    );
  }

  // Empty state
  if (trades.length === 0) {
    return (
      <div className={className}>
        <EmptyState message="No recent trades for this market" />
      </div>
    );
  }

  // Determine which trades to highlight as new
  const isNewTrade = (tradeId: string) => !seenTradeIds.has(tradeId) && showNewTrades;

  return (
    <div className={cn('space-y-1', className)}>
      {/* New activity banner */}
      {newTradeCount > 0 && !showNewTrades && (
        <NewActivityBanner count={newTradeCount} onClick={handleViewNewTrades} />
      )}

      {/* Trade list */}
      <div className="divide-y divide-gray-100">
        {trades.map((trade) => (
          <ActivityItem
            key={trade.id}
            trade={trade}
            className={isNewTrade(trade.id) ? 'bg-blue-50/50' : undefined}
          />
        ))}
      </div>

      {/* Load more / Refresh buttons */}
      <div className="flex items-center justify-center gap-3 pt-4">
        {hasMore && (
          <button
            type="button"
            onClick={handleLoadMore}
            disabled={isLoading}
            className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Loading...' : 'Load More'}
          </button>
        )}
        <button
          type="button"
          onClick={handleRefresh}
          disabled={isLoading}
          className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          aria-label="Refresh"
        >
          <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
        </button>
      </div>
    </div>
  );
}

export default ActivityFeed;
