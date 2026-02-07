/**
 * Order Book Component
 *
 * Sprint 04 - Data Visualization
 * PRD: orderbook_component, orderbook_loading_states, orderbook_depth_visual
 *
 * Features:
 * - Uses useOrderbook hook for real-time L2 order book data
 * - Horizontal bid/ask depth bars with size-relative widths
 * - Best bid and best ask prices shown prominently
 * - Spread displayed in cents and percentage
 * - Green for bids, red for asks (market convention)
 * - Configurable number of levels (default 5)
 * - Loading, empty, and error states
 * - Auto-retry with exponential backoff on failure
 * - Stale data indicator when data is older than 10s
 * - Hover state showing exact price and size details
 * - Animated bar changes on data updates (CSS transitions)
 * - Mid-price line between bids and asks
 */

'use client';

import { useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { useOrderbook, type OrderLevel } from '@/hooks';
import { cn } from '@/lib/utils';

/** Threshold in milliseconds after which data is considered stale */
const STALE_THRESHOLD_MS = 10000;

/**
 * Props for OrderBook component
 */
export interface OrderBookProps {
  /** Token ID to fetch order book for */
  tokenId: string | undefined | null;
  /** Number of levels to display on each side (default: 5) */
  levels?: number;
  /** Refetch interval in milliseconds (default: 5000) */
  refetchInterval?: number;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Props for OrderBookSkeleton component
 */
export interface OrderBookSkeletonProps {
  /** Number of skeleton rows to display per side (default: 5) */
  levels?: number;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Props for OrderBookError component
 */
export interface OrderBookErrorProps {
  /** Error message to display */
  error: string;
  /** Callback when retry button is clicked */
  onRetry?: () => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Props for OrderBookEmpty component
 */
export interface OrderBookEmptyProps {
  /** Message to display */
  message?: string;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Internal type for processed order level with relative size
 */
interface ProcessedLevel extends OrderLevel {
  /** Size as a percentage of the max size (0-100) for bar width */
  relativeSize: number;
}

/**
 * Format price as cents (e.g., "65¢")
 */
function formatPriceAsCents(price: string): string {
  const value = parseFloat(price);
  return `${Math.round(value * 100)}¢`;
}

/**
 * Format price as percentage (e.g., "65%")
 */
function formatPriceAsPercent(price: string): string {
  const value = parseFloat(price);
  return `${Math.round(value * 100)}%`;
}

/**
 * Format size for display (handles large numbers)
 */
function formatSize(size: string): string {
  const value = parseFloat(size);
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return value.toFixed(1);
}

/**
 * Calculate spread in cents and percentage
 */
function calculateSpread(bestAsk: string | null, bestBid: string | null): { cents: string; percent: string } | null {
  if (!bestAsk || !bestBid) return null;

  const ask = parseFloat(bestAsk);
  const bid = parseFloat(bestBid);

  if (ask <= 0 || bid <= 0) return null;

  const spreadCents = (ask - bid) * 100;
  const midPrice = (ask + bid) / 2;
  const spreadPercent = midPrice > 0 ? ((ask - bid) / midPrice) * 100 : 0;

  return {
    cents: spreadCents.toFixed(1),
    percent: spreadPercent.toFixed(2),
  };
}

/**
 * Process order levels to add relative sizes for bar widths
 */
function processLevels(levels: OrderLevel[], maxSize: number): ProcessedLevel[] {
  return levels.map((level) => ({
    ...level,
    relativeSize: maxSize > 0 ? (parseFloat(level.size) / maxSize) * 100 : 0,
  }));
}

/**
 * OrderBookSkeleton - Animated placeholder for initial loading
 */
export function OrderBookSkeleton({
  levels = 5,
  className,
}: OrderBookSkeletonProps) {
  return (
    <div
      className={cn('rounded-lg border border-gray-200 bg-white p-4', className)}
      data-testid="orderbook-skeleton"
    >
      {/* Header skeleton */}
      <div className="flex items-center justify-between mb-4">
        <div className="h-5 w-24 bg-gray-200 rounded animate-pulse" />
        <div className="h-4 w-32 bg-gray-200 rounded animate-pulse" />
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-3 gap-2 text-xs text-gray-500 font-medium mb-2 px-1">
        <div>Price</div>
        <div className="text-right">Size</div>
        <div className="text-right">Total</div>
      </div>

      {/* Ask levels (reverse order - highest at top) */}
      <div className="space-y-1 mb-3">
        {Array.from({ length: levels }).map((_, i) => (
          <div
            key={`ask-${i}`}
            className="grid grid-cols-3 gap-2 h-6 items-center"
          >
            <div className="h-4 w-12 bg-gray-200 rounded animate-pulse" />
            <div className="h-4 w-16 bg-gray-200 rounded animate-pulse ml-auto" />
            <div className="h-4 w-full bg-gray-100 rounded animate-pulse" />
          </div>
        ))}
      </div>

      {/* Spread skeleton */}
      <div className="flex justify-center py-2 border-y border-gray-100">
        <div className="h-4 w-40 bg-gray-200 rounded animate-pulse" />
      </div>

      {/* Bid levels */}
      <div className="space-y-1 mt-3">
        {Array.from({ length: levels }).map((_, i) => (
          <div
            key={`bid-${i}`}
            className="grid grid-cols-3 gap-2 h-6 items-center"
          >
            <div className="h-4 w-12 bg-gray-200 rounded animate-pulse" />
            <div className="h-4 w-16 bg-gray-200 rounded animate-pulse ml-auto" />
            <div className="h-4 w-full bg-gray-100 rounded animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * OrderBookError - Error state with retry option
 */
export function OrderBookError({
  error,
  onRetry,
  className,
}: OrderBookErrorProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-gray-200 bg-gray-50 p-6 flex flex-col items-center justify-center text-center',
        className
      )}
      data-testid="orderbook-error"
    >
      <span className="text-sm text-gray-500 mb-2">{error}</span>
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
 * OrderBookEmpty - Empty state when no data is available
 */
export function OrderBookEmpty({
  message = 'Order book unavailable',
  className,
}: OrderBookEmptyProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-gray-200 bg-gray-50 p-6 flex items-center justify-center text-sm text-gray-500',
        className
      )}
      data-testid="orderbook-empty"
    >
      {message}
    </div>
  );
}

/**
 * Props for OrderBookStaleIndicator component
 */
export interface OrderBookStaleIndicatorProps {
  /** Whether the data is stale */
  isStale: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * OrderBookStaleIndicator - Visual indicator when order book data is stale
 */
export function OrderBookStaleIndicator({
  isStale,
  className,
}: OrderBookStaleIndicatorProps) {
  if (!isStale) return null;

  return (
    <div
      className={cn(
        'flex items-center gap-1 text-xs text-amber-600',
        className
      )}
      data-testid="orderbook-stale-indicator"
      title="Order book data may be outdated"
    >
      <AlertCircle className="h-3 w-3" />
      <span>Stale</span>
    </div>
  );
}

/**
 * Single order level row
 */
interface OrderLevelRowProps {
  level: ProcessedLevel;
  side: 'bid' | 'ask';
  cumulativeSize: number;
  maxCumulativeSize: number;
}

/**
 * Hover tooltip for order level
 */
interface OrderLevelTooltipProps {
  level: ProcessedLevel;
  side: 'bid' | 'ask';
  cumulativeSize: number;
}

function OrderLevelTooltip({ level, side, cumulativeSize }: OrderLevelTooltipProps) {
  const isBid = side === 'bid';
  const sideLabel = isBid ? 'Bid' : 'Ask';
  const priceValue = parseFloat(level.price);
  const sizeValue = parseFloat(level.size);
  const notionalValue = priceValue * sizeValue;

  return (
    <div
      className={cn(
        'absolute z-20 bg-gray-900 text-white text-xs rounded-lg shadow-lg p-3 pointer-events-none',
        'min-w-[180px] -translate-x-1/2 left-1/2',
        // Position tooltip above the row
        '-top-2 -translate-y-full'
      )}
      data-testid="orderbook-level-tooltip"
    >
      {/* Arrow pointing down */}
      <div className="absolute left-1/2 -translate-x-1/2 -bottom-1 w-2 h-2 bg-gray-900 rotate-45" />

      <div className="space-y-1.5">
        {/* Side label */}
        <div className={cn('font-semibold', isBid ? 'text-green-400' : 'text-red-400')}>
          {sideLabel} Level
        </div>

        {/* Price details */}
        <div className="flex justify-between gap-4">
          <span className="text-gray-400">Price:</span>
          <span className="font-medium">
            {formatPriceAsCents(level.price)} ({formatPriceAsPercent(level.price)})
          </span>
        </div>

        {/* Size details */}
        <div className="flex justify-between gap-4">
          <span className="text-gray-400">Size:</span>
          <span className="font-medium">{parseFloat(level.size).toLocaleString()} shares</span>
        </div>

        {/* Cumulative */}
        <div className="flex justify-between gap-4">
          <span className="text-gray-400">Cumulative:</span>
          <span className="font-medium">{cumulativeSize.toLocaleString()} shares</span>
        </div>

        {/* Notional value */}
        <div className="flex justify-between gap-4 pt-1 border-t border-gray-700">
          <span className="text-gray-400">Notional:</span>
          <span className="font-medium">${notionalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        </div>
      </div>
    </div>
  );
}

function OrderLevelRow({ level, side, cumulativeSize, maxCumulativeSize }: OrderLevelRowProps) {
  const [isHovered, setIsHovered] = useState(false);
  const isBid = side === 'bid';
  const barColor = isBid ? 'bg-green-100' : 'bg-red-100';
  const hoverBarColor = isBid ? 'bg-green-200' : 'bg-red-200';
  const textColor = isBid ? 'text-green-700' : 'text-red-700';
  const cumulativePercent = maxCumulativeSize > 0 ? (cumulativeSize / maxCumulativeSize) * 100 : 0;

  return (
    <div
      className={cn(
        'relative grid grid-cols-3 gap-2 h-7 items-center text-xs cursor-pointer',
        'transition-colors duration-150',
        isHovered && 'bg-gray-50'
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      data-testid={`orderbook-level-${side}`}
    >
      {/* Background depth bar based on cumulative size - with transition animation */}
      <div
        className={cn(
          'absolute inset-y-0 right-0 opacity-50 transition-all duration-300 ease-out',
          isHovered ? hoverBarColor : barColor
        )}
        style={{ width: `${cumulativePercent}%` }}
      />

      {/* Price */}
      <span className={cn('relative z-10 font-medium', textColor)}>
        {formatPriceAsCents(level.price)}
      </span>

      {/* Size */}
      <span className="relative z-10 text-right text-gray-600">
        {formatSize(level.size)}
      </span>

      {/* Cumulative size */}
      <span className="relative z-10 text-right text-gray-500">
        {formatSize(cumulativeSize.toString())}
      </span>

      {/* Hover tooltip */}
      {isHovered && (
        <OrderLevelTooltip
          level={level}
          side={side}
          cumulativeSize={cumulativeSize}
        />
      )}
    </div>
  );
}

/**
 * OrderBook Component
 *
 * Displays a real-time L2 order book for a prediction market token.
 * Shows bid and ask levels with depth visualization.
 *
 * @example
 * ```tsx
 * // Basic usage
 * <OrderBook tokenId="71321045679252212594626385532706912750332728571942532289631379312455583286595" />
 *
 * // With custom levels
 * <OrderBook tokenId={tokenId} levels={10} />
 *
 * // Faster refresh
 * <OrderBook tokenId={tokenId} refetchInterval={2000} />
 * ```
 */
export function OrderBook({
  tokenId,
  levels = 5,
  refetchInterval = 5000,
  className,
}: OrderBookProps) {
  const {
    data,
    isLoading,
    error,
    refetch,
    dataUpdatedAt,
  } = useOrderbook(tokenId, { depth: levels, refetchInterval, enabled: !!tokenId });

  // Early return for missing token ID
  if (!tokenId) {
    return <OrderBookEmpty message="Select an outcome to view order book" className={className} />;
  }

  // Loading state
  if (isLoading) {
    return <OrderBookSkeleton levels={levels} className={className} />;
  }

  // Error state
  if (error) {
    return (
      <OrderBookError
        error={error instanceof Error ? error.message : 'Order book unavailable'}
        onRetry={() => refetch()}
        className={className}
      />
    );
  }

  // Empty state
  if (!data || (data.bids.length === 0 && data.asks.length === 0)) {
    return <OrderBookEmpty className={className} />;
  }

  // Determine if data is stale (older than 10 seconds)
  const isStale = dataUpdatedAt ? Date.now() - dataUpdatedAt > STALE_THRESHOLD_MS : false;

  // Get the levels we want to display
  const displayAsks = data.asks.slice(0, levels);
  const displayBids = data.bids.slice(0, levels);

  // Find max size for bar scaling across both sides
  const allSizes = [...displayAsks, ...displayBids].map((l) => parseFloat(l.size));
  const maxSize = Math.max(...allSizes, 0);

  // Process levels with relative sizes
  const processedAsks = processLevels(displayAsks, maxSize);
  const processedBids = processLevels(displayBids, maxSize);

  // Calculate cumulative sizes for depth bars
  const asksCumulative: number[] = [];
  let askTotal = 0;
  for (const ask of processedAsks) {
    askTotal += parseFloat(ask.size);
    asksCumulative.push(askTotal);
  }

  const bidsCumulative: number[] = [];
  let bidTotal = 0;
  for (const bid of processedBids) {
    bidTotal += parseFloat(bid.size);
    bidsCumulative.push(bidTotal);
  }

  const maxCumulativeSize = Math.max(
    asksCumulative[asksCumulative.length - 1] || 0,
    bidsCumulative[bidsCumulative.length - 1] || 0
  );

  // Calculate spread
  const spread = calculateSpread(data.bestAsk, data.bestBid);

  return (
    <div
      className={cn('rounded-lg border border-gray-200 bg-white p-4', className)}
      data-testid="orderbook"
    >
      {/* Header with title and stale indicator */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-900">Order Book</h3>
          <OrderBookStaleIndicator isStale={isStale} />
        </div>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-3 gap-2 text-xs text-gray-500 font-medium mb-2 px-0">
        <div>Price</div>
        <div className="text-right">Size</div>
        <div className="text-right">Total</div>
      </div>

      {/* Ask levels (reversed so best ask is closest to spread) */}
      <div className="space-y-0.5 mb-2">
        {processedAsks
          .slice()
          .reverse()
          .map((level, i) => {
            const originalIndex = processedAsks.length - 1 - i;
            return (
              <OrderLevelRow
                key={`ask-${level.price}`}
                level={level}
                side="ask"
                cumulativeSize={asksCumulative[originalIndex] ?? 0}
                maxCumulativeSize={maxCumulativeSize}
              />
            );
          })}
      </div>

      {/* Mid-price line and spread row - prominently displayed between asks and bids */}
      <div className="relative" data-testid="orderbook-mid-price-section">
        {/* Horizontal mid-price line spanning full width */}
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-0.5 bg-gradient-to-r from-green-300 via-indigo-400 to-red-300 opacity-60" />

        {/* Mid-price indicator diamond */}
        {data.midPrice && (
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
            <div className="w-3 h-3 bg-indigo-500 rotate-45 ring-2 ring-white shadow-md" />
          </div>
        )}

        {/* Spread info overlay */}
        <div className="relative flex items-center justify-center py-2.5 -mx-4 px-4">
          <div className="flex items-center gap-4 text-xs bg-white/90 backdrop-blur-sm px-3 py-1 rounded-full shadow-sm border border-gray-100">
            {/* Best Bid */}
            <div className="flex items-center gap-1">
              <span className="text-gray-500">Bid:</span>
              <span className="font-semibold text-green-700">
                {data.bestBid ? formatPriceAsCents(data.bestBid) : '—'}
              </span>
            </div>

            {/* Mid Price */}
            {data.midPrice && (
              <div className="flex items-center gap-1 px-2 border-x border-gray-200">
                <span className="text-gray-500">Mid:</span>
                <span className="font-semibold text-indigo-600">
                  {formatPriceAsCents(data.midPrice)}
                </span>
              </div>
            )}

            {/* Best Ask */}
            <div className="flex items-center gap-1">
              <span className="text-gray-500">Ask:</span>
              <span className="font-semibold text-red-700">
                {data.bestAsk ? formatPriceAsCents(data.bestAsk) : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Spread displayed below */}
        {spread && (
          <div className="flex justify-center -mt-1 mb-1">
            <span className="text-[10px] text-gray-400">
              Spread: {spread.cents}¢ ({spread.percent}%)
            </span>
          </div>
        )}
      </div>

      {/* Bid levels */}
      <div className="space-y-0.5 mt-2">
        {processedBids.map((level, i) => (
          <OrderLevelRow
            key={`bid-${level.price}`}
            level={level}
            side="bid"
            cumulativeSize={bidsCumulative[i] ?? 0}
            maxCumulativeSize={maxCumulativeSize}
          />
        ))}
      </div>

      {/* Tick size info */}
      <div className="mt-3 pt-2 border-t border-gray-100 text-xs text-gray-400">
        Tick: {formatPriceAsCents(data.tickSize)} | Min: {formatSize(data.minOrderSize)}
      </div>
    </div>
  );
}

export default OrderBook;
