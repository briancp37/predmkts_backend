'use client';

import { memo, useMemo } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Star, TrendingUp, TrendingDown, ExternalLink, Loader2 } from 'lucide-react';
import { cn, formatNumber } from '@/lib/utils';
import { DataTable, type Column } from '@/components/ui/data-table';
import type { AdvancedMarket } from '@/hooks/use-markets-advanced';

export interface MarketTableProps {
  /** Markets data to display */
  markets: AdvancedMarket[];
  /** Loading state */
  loading?: boolean;
  /** Set of watchlisted market IDs for quick lookup */
  watchlistedIds?: Set<string>;
  /** Market ID that has a pending watchlist operation */
  pendingWatchlistId?: string | null;
  /** Callback when watchlist toggle is clicked */
  onWatchlistToggle?: (marketId: string) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Category badge color mapping
 */
const categoryColors: Record<string, { bg: string; text: string }> = {
  politics: { bg: 'bg-blue-50', text: 'text-blue-700' },
  crypto: { bg: 'bg-orange-50', text: 'text-orange-700' },
  sports: { bg: 'bg-green-50', text: 'text-green-700' },
  finance: { bg: 'bg-emerald-50', text: 'text-emerald-700' },
  entertainment: { bg: 'bg-pink-50', text: 'text-pink-700' },
  tech: { bg: 'bg-cyan-50', text: 'text-cyan-700' },
  science: { bg: 'bg-violet-50', text: 'text-violet-700' },
  world: { bg: 'bg-amber-50', text: 'text-amber-700' },
  other: { bg: 'bg-gray-50', text: 'text-gray-700' },
};

/**
 * Get spread color based on spread percentage
 * Low spread (<2%) = green (good for trading)
 * Medium spread (2-5%) = yellow (moderate)
 * High spread (>5%) = red (wide spread)
 */
function getSpreadColor(spreadPercent: number | null): string {
  if (spreadPercent === null) return 'text-gray-500';
  if (spreadPercent < 2) return 'text-green-600';
  if (spreadPercent < 5) return 'text-yellow-600';
  return 'text-red-600';
}

/**
 * Format price as cents (0-100 scale typical for prediction markets)
 */
function formatPrice(price: number | null): string {
  if (price === null) return '—';
  return `${(price * 100).toFixed(1)}¢`;
}

/**
 * MarketTable Component
 *
 * Displays markets in a table view with all key information.
 * Uses the DataTable component as a base with custom column rendering.
 *
 * PRD #9 - Create MarketTable component for table view display
 * PRD #18 - Wrapped with React.memo for performance optimization
 */
export const MarketTable = memo(function MarketTable({
  markets,
  loading = false,
  watchlistedIds = new Set(),
  pendingWatchlistId = null,
  onWatchlistToggle,
  className,
}: MarketTableProps) {
  // Memoize columns to prevent recreating on every render
  const columns: Column<AdvancedMarket>[] = useMemo(() => [
    {
      key: 'question',
      header: 'Market',
      className: 'min-w-[250px] max-w-[400px]',
      render: (_, market) => {
        // Link to event detail page if eventSlug is available, otherwise use market slug
        const href = market.eventSlug
          ? `/event/${market.eventSlug}`
          : `/markets/${market.slug ?? market.polymarketId}`;
        return (
          <Link
            href={href}
            className="flex items-center gap-3 group"
          >
            {/* Market thumbnail */}
            <div className="relative h-10 w-10 flex-shrink-0 overflow-hidden rounded bg-gray-100">
              {market.slug ? (
                <Image
                  src={`https://polymarket.com/images/markets/${market.slug}.png`}
                  alt=""
                  fill
                  className="object-cover"
                  onError={(e) => {
                    const target = e.target as HTMLImageElement;
                    target.style.display = 'none';
                  }}
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-xs text-gray-400">
                  —
                </div>
              )}
            </div>
            {/* Market question */}
            <span className="line-clamp-2 text-sm font-medium text-gray-900 group-hover:text-indigo-600 transition-colors">
              {market.question}
            </span>
          </Link>
        );
      },
    },
    {
      key: 'priceChange24h',
      header: '24H Change',
      className: 'w-[100px] text-right hidden sm:table-cell',
      render: (_, market) => (
        <div className="flex items-center justify-end gap-1">
          {market.priceChange24h >= 0 ? (
            <TrendingUp className="h-3.5 w-3.5 text-green-500" />
          ) : (
            <TrendingDown className="h-3.5 w-3.5 text-red-500" />
          )}
          <span
            className={cn(
              'text-sm font-medium',
              market.priceChange24h >= 0 ? 'text-green-600' : 'text-red-600'
            )}
          >
            {market.priceChange24h >= 0 ? '+' : ''}
            {market.priceChange24h.toFixed(2)}%
          </span>
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      className: 'w-[100px] hidden md:table-cell',
      render: (_, market) => {
        const category = market.category?.toLowerCase() ?? 'other';
        const defaultStyle = { bg: 'bg-gray-50', text: 'text-gray-700' };
        const style = categoryColors[category] ?? defaultStyle;
        return (
          <span
            className={cn(
              'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
              style.bg,
              style.text
            )}
          >
            {market.category ?? 'Other'}
          </span>
        );
      },
    },
    {
      key: 'bid',
      header: 'Bid',
      className: 'w-[80px] text-right hidden lg:table-cell',
      render: (_, market) => (
        <span className="text-sm font-medium text-green-700">
          {formatPrice(market.bid)}
        </span>
      ),
    },
    {
      key: 'ask',
      header: 'Ask',
      className: 'w-[80px] text-right hidden lg:table-cell',
      render: (_, market) => (
        <span className="text-sm font-medium text-red-700">
          {formatPrice(market.ask)}
        </span>
      ),
    },
    {
      key: 'spreadPercent',
      header: 'Spread',
      className: 'w-[80px] text-right hidden lg:table-cell',
      render: (_, market) => (
        <span className={cn('text-sm font-medium', getSpreadColor(market.spreadPercent))}>
          {market.spreadPercent !== null ? `${market.spreadPercent.toFixed(2)}%` : '—'}
        </span>
      ),
    },
    {
      key: 'volume24h',
      header: 'Volume',
      className: 'w-[100px] text-right hidden sm:table-cell',
      render: (_, market) => (
        <span className="text-sm text-gray-900">
          ${formatNumber(market.volume24h)}
        </span>
      ),
    },
    {
      key: 'liquidity',
      header: 'Liquidity',
      className: 'w-[100px] text-right hidden md:table-cell',
      render: (_, market) => (
        <span className="text-sm text-gray-900">
          ${formatNumber(market.liquidity)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Action',
      className: 'w-[120px] text-right',
      render: (_, market) => {
        const isWatchlisted = watchlistedIds.has(market.id);
        const isPending = pendingWatchlistId === market.id;
        return (
          <div className="flex items-center justify-end gap-2">
            {/* Watchlist star */}
            {onWatchlistToggle && (
              <button
                type="button"
                disabled={isPending}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onWatchlistToggle(market.id);
                }}
                className={cn(
                  'rounded-full p-1.5 transition-colors',
                  isPending && 'opacity-70 cursor-not-allowed',
                  isWatchlisted
                    ? 'text-yellow-500 hover:text-yellow-600'
                    : 'text-gray-300 hover:text-yellow-500'
                )}
                aria-label={isWatchlisted ? 'Remove from watchlist' : 'Add to watchlist'}
              >
                {isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Star
                    className={cn('h-4 w-4', isWatchlisted && 'fill-current')}
                  />
                )}
              </button>
            )}
            {/* Trade button */}
            <a
              href={`https://polymarket.com/event/${market.slug ?? market.polymarketId}`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className={cn(
                'inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium',
                'bg-indigo-600 text-white transition-colors hover:bg-indigo-700',
                'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1'
              )}
            >
              Trade
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        );
      },
    },
  ], [watchlistedIds, pendingWatchlistId, onWatchlistToggle]);

  return (
    <DataTable
      data={markets}
      columns={columns}
      loading={loading}
      emptyMessage="No markets match your filters"
      className={className}
    />
  );
});

// Display name for debugging
MarketTable.displayName = 'MarketTable';

export default MarketTable;
