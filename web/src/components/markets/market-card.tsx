'use client';

import { memo, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Star, TrendingUp, TrendingDown, ExternalLink } from 'lucide-react';
import { cn, formatNumber, formatDate } from '@/lib/utils';
import type { AdvancedMarket } from '@/hooks/use-markets-advanced';

export interface MarketCardProps {
  /** Market data to display */
  market: AdvancedMarket;
  /** Whether the market is in the user's watchlist */
  isWatchlisted?: boolean;
  /** Callback when watchlist toggle is clicked */
  onWatchlistToggle?: (marketId: string) => void;
  /** Callback when card is clicked (navigation) */
  onClick?: () => void;
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
 * MarketCard Component
 *
 * Displays a market card for the card view on the Markets page.
 * Shows market info, CLOB bid/ask prices, spread, volume, liquidity,
 * and 24h change with appropriate styling.
 *
 * PRD #8 - Create MarketCard component for card view display
 * PRD #18 - Wrapped with React.memo for performance optimization
 */
export const MarketCard = memo(function MarketCard({
  market,
  isWatchlisted = false,
  onWatchlistToggle,
  onClick,
  className,
}: MarketCardProps) {
  const [imageError, setImageError] = useState(false);
  const category = market.category?.toLowerCase() ?? 'other';
  const defaultStyle = { bg: 'bg-gray-50', text: 'text-gray-700' };
  const categoryStyle = categoryColors[category] ?? defaultStyle;

  // Use imageUrl from API, fallback to gradient if not available or errored
  const hasImage = market.imageUrl && !imageError;

  const handleWatchlistClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onWatchlistToggle?.(market.id);
  };

  const handleTradeClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Open Polymarket in new tab
    window.open(
      `https://polymarket.com/event/${market.slug ?? market.polymarketId}`,
      '_blank',
      'noopener,noreferrer'
    );
  };

  const cardContent = (
    <div
      className={cn(
        'group relative flex h-full flex-col rounded-lg border border-gray-200 bg-white shadow-sm',
        'transition-all duration-200 hover:border-indigo-200 hover:shadow-md',
        className
      )}
    >
      {/* Market Header - Image or category-based gradient background */}
      <div className={cn(
        'relative h-32 w-full overflow-hidden rounded-t-lg',
        // Category-based gradient backgrounds (fallback when no image)
        !hasImage && category === 'politics' && 'bg-gradient-to-br from-blue-500 to-blue-700',
        !hasImage && category === 'crypto' && 'bg-gradient-to-br from-orange-500 to-amber-600',
        !hasImage && category === 'sports' && 'bg-gradient-to-br from-green-500 to-emerald-600',
        !hasImage && category === 'finance' && 'bg-gradient-to-br from-emerald-500 to-teal-600',
        !hasImage && category === 'entertainment' && 'bg-gradient-to-br from-pink-500 to-rose-600',
        !hasImage && category === 'tech' && 'bg-gradient-to-br from-cyan-500 to-blue-600',
        !hasImage && category === 'science' && 'bg-gradient-to-br from-violet-500 to-purple-600',
        !hasImage && category === 'world' && 'bg-gradient-to-br from-amber-500 to-orange-600',
        !hasImage && !category && 'bg-gradient-to-br from-gray-500 to-gray-700',
        !hasImage && (!['politics', 'crypto', 'sports', 'finance', 'entertainment', 'tech', 'science', 'world'].includes(category || '')) && 'bg-gradient-to-br from-indigo-500 to-purple-600',
        hasImage && 'bg-gray-200'
      )}>
        {/* Market image if available */}
        {hasImage && (
          <Image
            src={market.imageUrl!}
            alt={market.question}
            fill
            className="object-cover transition-transform duration-200 group-hover:scale-105"
            onError={() => setImageError(true)}
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
          />
        )}
        {/* Decorative pattern overlay (only for gradient fallback) */}
        {!hasImage && (
          <div className="absolute inset-0 opacity-10">
            <div className="absolute inset-0" style={{
              backgroundImage: 'radial-gradient(circle at 25% 25%, white 1px, transparent 1px)',
              backgroundSize: '20px 20px'
            }} />
          </div>
        )}
        {/* Gradient overlay for depth/readability */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent" />

        {/* Watchlist Star */}
        {onWatchlistToggle && (
          <button
            type="button"
            onClick={handleWatchlistClick}
            className={cn(
              'absolute right-2 top-2 rounded-full p-1.5 transition-colors',
              isWatchlisted
                ? 'bg-yellow-400 text-white hover:bg-yellow-500'
                : 'bg-white/80 text-gray-400 hover:bg-white hover:text-yellow-500'
            )}
            aria-label={isWatchlisted ? 'Remove from watchlist' : 'Add to watchlist'}
          >
            <Star
              className={cn('h-4 w-4', isWatchlisted && 'fill-current')}
            />
          </button>
        )}
      </div>

      {/* Card Content */}
      <div className="flex flex-1 flex-col p-4">
        {/* Category Badge */}
        <div className="mb-2">
          <span
            className={cn(
              'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
              categoryStyle.bg,
              categoryStyle.text
            )}
          >
            {market.category ?? 'Other'}
          </span>
        </div>

        {/* Market Question */}
        <h3 className="mb-3 line-clamp-2 flex-1 text-sm font-semibold text-gray-900 group-hover:text-indigo-600">
          {market.question}
        </h3>

        {/* Bid/Ask Prices */}
        <div className="mb-3 grid grid-cols-2 gap-2">
          <div className="rounded-md bg-green-50 px-2 py-1.5">
            <div className="text-xs text-gray-500">Bid</div>
            <div className="text-sm font-semibold text-green-700">
              {formatPrice(market.bid)}
            </div>
          </div>
          <div className="rounded-md bg-red-50 px-2 py-1.5">
            <div className="text-xs text-gray-500">Ask</div>
            <div className="text-sm font-semibold text-red-700">
              {formatPrice(market.ask)}
            </div>
          </div>
        </div>

        {/* Spread */}
        <div className="mb-3 flex items-center justify-between text-sm">
          <span className="text-gray-500">Spread</span>
          <span className={cn('font-medium', getSpreadColor(market.spreadPercent))}>
            {market.spreadPercent !== null
              ? `${market.spreadPercent.toFixed(2)}%`
              : '—'}
            {market.spreadCents !== null && (
              <span className="ml-1 text-xs text-gray-400">
                ({market.spreadCents.toFixed(1)}¢)
              </span>
            )}
          </span>
        </div>

        {/* Stats Row */}
        <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
          <div>
            <div className="text-xs text-gray-500">24h Vol</div>
            <div className="font-medium text-gray-900">
              ${formatNumber(market.volume24h)}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Liquidity</div>
            <div className="font-medium text-gray-900">
              ${formatNumber(market.liquidity)}
            </div>
          </div>
        </div>

        {/* 24h Change */}
        <div className="mb-4 flex items-center justify-between text-sm">
          <span className="text-gray-500">24h Change</span>
          <div className="flex items-center gap-1">
            {market.priceChange24h >= 0 ? (
              <TrendingUp className="h-4 w-4 text-green-500" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-500" />
            )}
            <span
              className={cn(
                'font-medium',
                market.priceChange24h >= 0 ? 'text-green-600' : 'text-red-600'
              )}
            >
              {market.priceChange24h >= 0 ? '+' : ''}
              {market.priceChange24h.toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Trade Button */}
        <button
          type="button"
          onClick={handleTradeClick}
          className={cn(
            'flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium',
            'bg-indigo-600 text-white transition-colors hover:bg-indigo-700',
            'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2'
          )}
        >
          Trade
          <ExternalLink className="h-4 w-4" />
        </button>
      </div>

      {/* End Date Footer */}
      {market.endDate && (
        <div className="border-t border-gray-100 px-4 py-2">
          <span className="text-xs text-gray-500">
            Ends {formatDate(market.endDate)}
          </span>
        </div>
      )}
    </div>
  );

  // Wrap in Link if onClick is not provided
  if (!onClick && market.slug) {
    return (
      <Link href={`/markets/${market.slug}`} className="block h-full">
        {cardContent}
      </Link>
    );
  }

  // Otherwise use onClick handler
  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={onClick ? 'cursor-pointer' : undefined}
    >
      {cardContent}
    </div>
  );
});

// Display name for debugging
MarketCard.displayName = 'MarketCard';

export default MarketCard;
