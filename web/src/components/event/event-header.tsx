/**
 * Event Header Component
 *
 * Displays the main header for an event detail page including:
 * - Event title with proper typography
 * - Category tags as colored badges
 * - Primary probability as large percentage display
 * - Volume with proper formatting
 * - End date with relative time
 * - Watchlist toggle button for authenticated users
 */

'use client';

import { memo, useMemo } from 'react';
import { Star, Calendar, DollarSign } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { LargeProbabilityDisplay, ProbabilityChange } from './probability-display';
import { useAuth } from '@/lib/api/auth-context';
import { useWatchlist, useAddToWatchlist, useRemoveFromWatchlist } from '@/hooks/use-watchlist';

// ============================================================================
// Category Color Mapping
// ============================================================================

const CATEGORY_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  Politics: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  Crypto: { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' },
  Tech: { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200' },
  Sports: { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' },
  Entertainment: { bg: 'bg-pink-50', text: 'text-pink-700', border: 'border-pink-200' },
  Science: { bg: 'bg-cyan-50', text: 'text-cyan-700', border: 'border-cyan-200' },
  Economics: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
  Finance: { bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200' },
  World: { bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-200' },
  Business: { bg: 'bg-slate-50', text: 'text-slate-700', border: 'border-slate-200' },
};

const DEFAULT_CATEGORY_COLORS = { bg: 'bg-gray-50', text: 'text-gray-700', border: 'border-gray-200' };

/**
 * Get color classes for a category
 */
function getCategoryColors(category: string): { bg: string; text: string; border: string } {
  return CATEGORY_COLORS[category] || DEFAULT_CATEGORY_COLORS;
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format a currency value with proper abbreviations
 * @param value - The value in USD
 * @returns Formatted string like "$66.1K" or "$1.2M"
 */
export function formatVolume(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
}

/**
 * Format a date as relative time or absolute date
 * @param dateString - ISO 8601 date string
 * @returns Formatted string like "Ends Jun 30, 2026" or "Ended 2 days ago"
 */
export function formatEndDate(dateString: string): { text: string; isPast: boolean } {
  const date = new Date(dateString);
  const now = new Date();
  const isPast = date < now;

  const diffMs = Math.abs(date.getTime() - now.getTime());
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  // Format the date for display
  const formattedDate = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  if (isPast) {
    if (diffDays === 0) {
      return { text: 'Ended today', isPast };
    }
    if (diffDays === 1) {
      return { text: 'Ended yesterday', isPast };
    }
    if (diffDays < 7) {
      return { text: `Ended ${diffDays} days ago`, isPast };
    }
    return { text: `Ended ${formattedDate}`, isPast };
  }

  // Future date
  if (diffDays === 0) {
    return { text: 'Ends today', isPast };
  }
  if (diffDays === 1) {
    return { text: 'Ends tomorrow', isPast };
  }
  if (diffDays < 7) {
    return { text: `Ends in ${diffDays} days`, isPast };
  }
  return { text: `Ends ${formattedDate}`, isPast };
}

// ============================================================================
// CategoryBadge Component
// ============================================================================

export interface CategoryBadgeProps {
  category: string;
  className?: string;
}

/**
 * Category badge with predefined color mapping
 */
export const CategoryBadge = memo(function CategoryBadge({
  category,
  className,
}: CategoryBadgeProps) {
  const colors = getCategoryColors(category);

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border',
        colors.bg,
        colors.text,
        colors.border,
        className
      )}
    >
      {category}
    </span>
  );
});

// ============================================================================
// WatchlistButton Component
// ============================================================================

interface WatchlistButtonProps {
  marketId: string;
  className?: string;
}

/**
 * Watchlist toggle button for authenticated users
 */
const WatchlistButton = memo(function WatchlistButton({
  marketId,
  className,
}: WatchlistButtonProps) {
  const { user } = useAuth();
  const { data: watchlist } = useWatchlist({ enabled: !!user });
  const { mutate: addToWatchlist, isPending: isAdding } = useAddToWatchlist();
  const { mutate: removeFromWatchlist, isPending: isRemoving } = useRemoveFromWatchlist();

  const isWatchlisted = watchlist?.marketIds.includes(marketId) ?? false;
  const isPending = isAdding || isRemoving;

  // Don't show button if user is not authenticated
  if (!user) {
    return null;
  }

  const handleClick = () => {
    if (isPending) return;

    if (isWatchlisted) {
      removeFromWatchlist(marketId);
    } else {
      addToWatchlist(marketId);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isPending}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
        isWatchlisted
          ? 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200'
          : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
        isPending && 'opacity-50 cursor-not-allowed',
        className
      )}
      aria-label={isWatchlisted ? 'Remove from watchlist' : 'Add to watchlist'}
    >
      <Star
        className={cn('h-4 w-4', isWatchlisted && 'fill-current')}
      />
      <span>{isWatchlisted ? 'Watching' : 'Watch'}</span>
    </button>
  );
});

// ============================================================================
// EventHeader Component
// ============================================================================

export interface EventHeaderProps {
  /** Event title */
  title: string;
  /** Event category (e.g., "Politics", "Crypto") */
  category?: string | null;
  /** Primary probability (0.0 to 1.0) - typically the "Yes" outcome */
  probability?: number | null;
  /** 24-hour probability change (e.g., 0.05 for 5% increase) */
  probabilityChange24h?: number | null;
  /** Total trading volume in USD */
  volume?: number | null;
  /** End date as ISO 8601 string */
  endDate?: string | null;
  /** Market ID for watchlist functionality */
  marketId?: string | null;
  /** Whether the market is resolved */
  resolved?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Event header component with title, probability, metadata, and watchlist toggle.
 *
 * @example
 * ```tsx
 * <EventHeader
 *   title="Will Bitcoin reach $100K by end of 2025?"
 *   category="Crypto"
 *   probability={0.12}
 *   probabilityChange24h={0.02}
 *   volume={66109}
 *   endDate="2025-12-31T23:59:59Z"
 *   marketId="market-123"
 * />
 * ```
 */
export const EventHeader = memo(function EventHeader({
  title,
  category,
  probability,
  probabilityChange24h,
  volume,
  endDate,
  marketId,
  resolved = false,
  className,
}: EventHeaderProps) {
  // Memoize formatted end date
  const formattedEndDate = useMemo(() => {
    if (!endDate) return null;
    return formatEndDate(endDate);
  }, [endDate]);

  return (
    <Card className={className}>
      <CardContent className="pt-6 space-y-4">
        {/* Top row: Category badge and Watchlist button */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {category && <CategoryBadge category={category} />}
            {resolved && (
              <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 border border-gray-200">
                Resolved
              </span>
            )}
          </div>
          {marketId && <WatchlistButton marketId={marketId} />}
        </div>

        {/* Title */}
        <h1 className="text-2xl font-bold text-gray-900 md:text-3xl leading-tight">
          {title}
        </h1>

        {/* Probability and metadata row */}
        <div className="flex flex-wrap items-end justify-between gap-4 pt-2 border-t border-gray-100">
          {/* Left side: Probability display */}
          <div className="flex items-end gap-6">
            {probability !== null && probability !== undefined && (
              <div className="flex items-end gap-3">
                <LargeProbabilityDisplay
                  value={probability}
                  showChanceSuffix
                />
                {probabilityChange24h !== null && probabilityChange24h !== undefined && probabilityChange24h !== 0 && (
                  <div className="flex items-center gap-1 pb-1">
                    <ProbabilityChange change={probabilityChange24h} size="md" />
                    <span className="text-xs text-gray-400">24h</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right side: Volume and End Date */}
          <div className="flex items-center gap-4 text-sm text-gray-500">
            {volume !== null && volume !== undefined && (
              <div className="flex items-center gap-1.5">
                <DollarSign className="h-4 w-4" />
                <span>{formatVolume(volume)} Vol.</span>
              </div>
            )}
            {formattedEndDate && (
              <div className={cn(
                'flex items-center gap-1.5',
                formattedEndDate.isPast && 'text-gray-400'
              )}>
                <Calendar className="h-4 w-4" />
                <span>{formattedEndDate.text}</span>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
});
