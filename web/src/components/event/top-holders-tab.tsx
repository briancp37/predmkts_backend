/**
 * Top Holders Tab Component
 *
 * Sprint 05 - Activity and Social
 * PRD: top_holders_tab, top_holders_item
 *
 * Features:
 * - Display top holders for a market using useTopHolders hook
 * - Table with Rank, Wallet (truncated), Position, Value columns
 * - Medal icons for top 3 (🥇 🥈 🥉)
 * - Copy button for wallet addresses
 * - Wallet address links to trader profile
 * - Loading skeleton during fetch
 * - Empty state when no holders
 * - Hover state with details
 */

'use client';

import * as React from 'react';
import { Users, RefreshCw, AlertCircle, Copy, Check, ExternalLink } from 'lucide-react';
import { cn, shortenAddress, formatNumber } from '@/lib/utils';
import { useTopHolders, TopHolder } from '@/hooks/use-polymarket-proxy';

// =============================================================================
// Types
// =============================================================================

export interface TopHoldersTabProps {
  /** Condition ID for fetching market-specific holders */
  conditionId: string;
  /** Maximum number of holders to display */
  limit?: number;
  /** Optional className for the container */
  className?: string;
}

export interface TopHolderRowProps {
  /** Holder data */
  holder: TopHolder;
  /** Rank position (1-indexed) */
  rank: number;
  /** Optional className */
  className?: string;
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Get medal icon for top 3 positions
 */
function getRankDisplay(rank: number): React.ReactNode {
  switch (rank) {
    case 1:
      return <span className="text-lg" role="img" aria-label="1st place">🥇</span>;
    case 2:
      return <span className="text-lg" role="img" aria-label="2nd place">🥈</span>;
    case 3:
      return <span className="text-lg" role="img" aria-label="3rd place">🥉</span>;
    default:
      return <span className="text-sm font-medium text-gray-500 w-6 text-center">{rank}</span>;
  }
}

/**
 * Format position size in shares
 */
function formatShares(amount: string): string {
  const num = parseFloat(amount);
  if (isNaN(num)) return '0';
  return formatNumber(num);
}

/**
 * Format position value in dollars
 * Note: Currently we don't have price data, so we estimate using 50¢ average
 * TODO: When price data is available, calculate actual value
 */
function formatValue(amount: string, price: number = 0.5): string {
  const shares = parseFloat(amount);
  if (isNaN(shares)) return '$0';
  const value = shares * price;
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}k`;
  }
  if (value >= 1) {
    return `$${value.toFixed(2)}`;
  }
  return `$${value.toFixed(4)}`;
}

/**
 * Get outcome label from outcome index
 */
function getOutcomeLabel(outcomeIndex: number | null): string {
  if (outcomeIndex === null) return '';
  return outcomeIndex === 0 ? 'Yes' : 'No';
}

/**
 * Get outcome color classes
 */
function getOutcomeColorClasses(outcomeIndex: number | null): string {
  if (outcomeIndex === 0) return 'bg-green-100 text-green-700';
  if (outcomeIndex === 1) return 'bg-red-100 text-red-700';
  return 'bg-gray-100 text-gray-700';
}

// =============================================================================
// Copy Button Component
// =============================================================================

interface CopyButtonProps {
  text: string;
  className?: string;
}

function CopyButton({ text, className }: CopyButtonProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Silently fail if clipboard access is denied
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        'p-1 rounded hover:bg-gray-200 transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500',
        className
      )}
      aria-label={copied ? 'Copied!' : 'Copy address'}
      title={copied ? 'Copied!' : 'Copy address'}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-green-600" />
      ) : (
        <Copy className="h-3.5 w-3.5 text-gray-400" />
      )}
    </button>
  );
}

// =============================================================================
// Top Holder Row Component
// =============================================================================

/**
 * TopHolderRow - Single holder row display
 */
export function TopHolderRow({ holder, rank, className }: TopHolderRowProps) {
  const displayName = holder.pseudonym || holder.name || shortenAddress(holder.walletAddress);
  const outcomeLabel = getOutcomeLabel(holder.outcomeIndex);
  const outcomeColorClasses = getOutcomeColorClasses(holder.outcomeIndex);

  return (
    <div
      className={cn(
        'flex items-center gap-3 py-3 px-2 rounded-lg',
        'hover:bg-gray-50 transition-colors duration-150 group',
        className
      )}
    >
      {/* Rank */}
      <div className="flex-shrink-0 w-8 flex items-center justify-center">
        {getRankDisplay(rank)}
      </div>

      {/* Avatar placeholder - colored circle based on outcome */}
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          outcomeColorClasses
        )}
      >
        <span className="text-xs font-medium">
          {holder.walletAddress.slice(2, 4).toUpperCase()}
        </span>
      </div>

      {/* Wallet info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {/* Wallet address - clickable to trader profile */}
          <a
            href={`/traders/${holder.walletAddress}`}
            className="font-mono text-sm text-gray-700 hover:text-indigo-600 truncate transition-colors"
          >
            {displayName}
          </a>
          {/* Copy button */}
          <CopyButton
            text={holder.walletAddress}
            className="opacity-0 group-hover:opacity-100"
          />
          {/* External link icon */}
          <a
            href={`/traders/${holder.walletAddress}`}
            className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-gray-200 transition-all"
            aria-label="View trader profile"
          >
            <ExternalLink className="h-3.5 w-3.5 text-gray-400" />
          </a>
        </div>
        {/* Outcome badge */}
        {outcomeLabel && (
          <span
            className={cn(
              'inline-block mt-1 px-1.5 py-0.5 text-xs font-medium rounded',
              outcomeColorClasses
            )}
          >
            {outcomeLabel}
          </span>
        )}
      </div>

      {/* Position size */}
      <div className="flex-shrink-0 text-right">
        <div className="text-sm font-medium text-gray-900">
          {formatShares(holder.amount)}
        </div>
        <div className="text-xs text-gray-500">shares</div>
      </div>

      {/* Position value */}
      <div className="flex-shrink-0 w-20 text-right">
        <div className="text-sm font-semibold text-gray-900">
          {formatValue(holder.amount)}
        </div>
        <div className="text-xs text-gray-400">est. value</div>
      </div>
    </div>
  );
}

// =============================================================================
// Loading Skeleton
// =============================================================================

/**
 * TopHoldersSkeleton - Animated loading placeholder
 */
export function TopHoldersSkeleton() {
  return (
    <div className="space-y-1">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 py-3 px-2 animate-pulse"
        >
          {/* Rank skeleton */}
          <div className="w-8 h-6 bg-gray-200 rounded" />

          {/* Avatar skeleton */}
          <div className="w-8 h-8 rounded-full bg-gray-200" />

          {/* Text skeletons */}
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-gray-200 rounded w-2/3" />
            <div className="h-3 bg-gray-200 rounded w-1/4" />
          </div>

          {/* Value skeletons */}
          <div className="space-y-1 text-right">
            <div className="h-4 bg-gray-200 rounded w-12 ml-auto" />
            <div className="h-3 bg-gray-200 rounded w-8 ml-auto" />
          </div>
          <div className="w-20 space-y-1 text-right">
            <div className="h-4 bg-gray-200 rounded w-16 ml-auto" />
            <div className="h-3 bg-gray-200 rounded w-12 ml-auto" />
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

function EmptyState({ message = 'No top holders found' }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-4">
        <Users className="h-6 w-6 text-gray-400" />
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

function ErrorState({ message = 'Failed to load top holders', onRetry }: ErrorStateProps) {
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
// Top Holders Tab Component
// =============================================================================

/**
 * TopHoldersTab - Top holders display for a market
 */
export function TopHoldersTab({
  conditionId,
  limit = 20,
  className,
}: TopHoldersTabProps) {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useTopHolders(conditionId, { limit });

  const holders = data?.holders ?? [];

  // Handle manual refresh
  const handleRefresh = () => {
    refetch();
  };

  // Loading state
  if (isLoading && holders.length === 0) {
    return (
      <div className={className}>
        <TopHoldersSkeleton />
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className={className}>
        <ErrorState
          message={error instanceof Error ? error.message : 'Failed to load top holders'}
          onRetry={handleRefresh}
        />
      </div>
    );
  }

  // Empty state
  if (holders.length === 0) {
    return (
      <div className={className}>
        <EmptyState message="No holders found for this market" />
      </div>
    );
  }

  return (
    <div className={cn('space-y-1', className)}>
      {/* Header with column labels */}
      <div className="flex items-center gap-3 py-2 px-2 text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-100">
        <div className="w-8 text-center">Rank</div>
        <div className="w-8" /> {/* Avatar spacer */}
        <div className="flex-1">Wallet</div>
        <div className="text-right">Position</div>
        <div className="w-20 text-right">Value</div>
      </div>

      {/* Holders list */}
      <div className="divide-y divide-gray-100">
        {holders.map((holder, index) => (
          <TopHolderRow
            key={holder.walletAddress}
            holder={holder}
            rank={index + 1}
          />
        ))}
      </div>

      {/* Refresh button */}
      <div className="flex items-center justify-center pt-4">
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

export default TopHoldersTab;
