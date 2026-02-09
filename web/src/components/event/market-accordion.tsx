/**
 * Market Accordion Component
 *
 * Sprint 07 - Expandable Market Accordion
 * PRD: market_accordion_container, market_accordion_header, market_accordion_content,
 *      accordion_loading_states
 *
 * Features:
 * - Expandable market rows using Radix Accordion
 * - Supports 'single' mode (only one market open) and 'multiple' mode
 * - Smooth height animation on expand/collapse
 * - Keyboard navigation (arrow keys, enter, space)
 * - URL hash persistence for deep linking to specific markets
 * - Accepts markets array with outcomes, tokenIds, and metadata
 * - Enhanced header with probability display, bid/ask spread, volume indicators
 * - Color-coded probability badges and price change indicators
 * - Subtle hover/selected state feedback
 * - Tabbed interface with Order Book, Graph, and Resolution tabs
 * - Lazy loading of tab content to avoid fetching data for collapsed markets
 * - Smooth fade-in animation when content appears
 * - Loading states with skeleton placeholders
 * - Error states with retry buttons
 */

'use client';

import * as React from 'react';
import { useCallback, useEffect, useState, useMemo, memo, useRef } from 'react';
import * as Accordion from '@radix-ui/react-accordion';
import * as Tabs from '@radix-ui/react-tabs';
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown, BookOpen, LineChart, FileText, AlertCircle, RefreshCw, Search, ArrowUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  formatProbability,
  formatProbabilityAsCents,
  getProbabilityColor,
} from './probability-display';
import { OrderBook, OrderBookSkeleton } from './order-book';
import { PriceChart } from './price-chart';
import { TimeRangeSelector, TIME_RANGE_TO_INTERVAL, DEFAULT_TIME_RANGE, type TimeRange } from './time-range-selector';
import { ResolutionRules } from './resolution-rules';
import { useRealtimePrices, useOrderbook } from '@/hooks';

/**
 * Outcome data for a market
 */
export interface MarketOutcome {
  /** Unique outcome identifier */
  id: string;
  /** CLOB token ID for this outcome */
  tokenId: string;
  /** Human-readable outcome name (e.g., "Yes", "No", "Kevin Warsh") */
  outcomeName: string;
  /** Current price (0.0 to 1.0) */
  currentPrice: number;
  /** 24-hour price change (0.0 to 1.0 delta) */
  priceChange24h?: number;
  /** Best bid price (0.0 to 1.0) from order book */
  bestBid?: number;
  /** Best ask price (0.0 to 1.0) from order book */
  bestAsk?: number;
}

/**
 * Market data for the accordion
 */
export interface AccordionMarket {
  /** Unique market identifier */
  id: string;
  /** Market question/title */
  question: string;
  /** List of outcomes with prices */
  outcomes: MarketOutcome[];
  /** Total trading volume */
  totalVolume: number;
  /** Current liquidity */
  liquidity: number;
  /** 24-hour trading volume */
  volume24h?: number;
  /** Optional image URL for candidate/outcome avatar */
  imageUrl?: string;
  /** Market description for resolution rules */
  description?: string;
  /** Resolver type for resolution rules */
  resolverType?: string;
  /** Resolution source for resolution rules */
  resolutionSource?: string;
  /** Whether the market is resolved */
  isResolved?: boolean;
  /** Resolution outcome if resolved */
  resolutionOutcome?: string;
}

/**
 * Tab values for accordion content
 */
export type AccordionTabValue = 'orderbook' | 'graph' | 'resolution';

/**
 * Accordion expansion mode
 */
export type AccordionMode = 'single' | 'multiple';

/**
 * Trade selection data passed to onTradeClick callback
 */
export interface TradeSelection {
  /** Market ID */
  marketId: string;
  /** Outcome ID (e.g., "yes" or "no") */
  outcomeId: string;
  /** Token ID for trading */
  tokenId: string;
  /** Outcome name (e.g., "Yes", "No") */
  outcomeName: string;
  /** Current price (0.0 to 1.0) */
  currentPrice: number;
  /** Trade direction */
  direction: 'buy';
}

/**
 * Real-time price update configuration
 */
export interface RealtimePriceConfig {
  /** Enable real-time price updates */
  enabled?: boolean;
  /** Polling interval in milliseconds (default: 10000) */
  refetchInterval?: number;
  /** Pause polling when all markets are collapsed (default: true) */
  pauseWhenCollapsed?: boolean;
}

export interface MarketAccordionProps {
  /** List of markets to display */
  markets: AccordionMarket[];
  /** Expansion mode: 'single' allows one open, 'multiple' allows many */
  mode?: AccordionMode;
  /** Default expanded market ID(s) */
  defaultExpanded?: string | string[];
  /** Callback when expansion changes */
  onExpandChange?: (expandedIds: string[]) => void;
  /** Callback when a buy button is clicked */
  onTradeClick?: (selection: TradeSelection) => void;
  /** Whether to sync expanded state with URL hash */
  persistToUrl?: boolean;
  /** Real-time price update configuration */
  realtimePrices?: RealtimePriceConfig;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Parse URL hash to get expanded market IDs
 */
function parseHashToMarketIds(): string[] {
  if (typeof window === 'undefined') return [];

  const hash = window.location.hash.slice(1); // Remove leading #
  if (!hash) return [];

  // Support both single ID and comma-separated IDs
  // Format: #market-{id} or #markets-{id1},{id2}
  if (hash.startsWith('market-')) {
    return [hash.slice(7)]; // Remove 'market-' prefix
  }
  if (hash.startsWith('markets-')) {
    return hash.slice(8).split(',').filter(Boolean);
  }

  return [];
}

/**
 * Generate URL hash from expanded market IDs
 */
function marketIdsToHash(ids: string[]): string {
  if (ids.length === 0) return '';
  if (ids.length === 1) return `market-${ids[0]}`;
  return `markets-${ids.join(',')}`;
}

/**
 * MarketAccordion - Expandable market rows with tabs for Order Book, Graph, Resolution
 *
 * Implements Polymarket-style expandable rows where each market can be clicked
 * to expand inline, showing detailed market information.
 */
export function MarketAccordion({
  markets,
  mode = 'single',
  defaultExpanded,
  onExpandChange,
  onTradeClick,
  persistToUrl = true,
  realtimePrices,
  className,
}: MarketAccordionProps) {
  // Initialize expanded state from URL hash or defaultExpanded
  const [expandedIds, setExpandedIds] = useState<string[]>(() => {
    if (persistToUrl) {
      const hashIds = parseHashToMarketIds();
      if (hashIds.length > 0) {
        // In single mode, only use first ID
        return mode === 'single' ? hashIds.slice(0, 1) : hashIds;
      }
    }

    if (defaultExpanded) {
      const ids = Array.isArray(defaultExpanded) ? defaultExpanded : [defaultExpanded];
      return mode === 'single' ? ids.slice(0, 1) : ids;
    }

    return [];
  });

  // Real-time price updates
  const marketIds = useMemo(() => markets.map((m) => m.id), [markets]);
  const { prices: realtimePriceData, lastUpdated: pricesLastUpdated } = useRealtimePrices(
    marketIds,
    {
      enabled: realtimePrices?.enabled ?? false,
      refetchInterval: realtimePrices?.refetchInterval ?? 10000,
      pauseWhenCollapsed: realtimePrices?.pauseWhenCollapsed ?? true,
      expandedMarketIds: expandedIds,
    }
  );

  // Merge real-time prices into markets
  const marketsWithRealtimePrices = useMemo(() => {
    if (!realtimePrices?.enabled || Object.keys(realtimePriceData).length === 0) {
      return markets;
    }

    return markets.map((market) => {
      const priceUpdate = realtimePriceData[market.id];
      if (!priceUpdate) return market;

      // Update outcomes with real-time prices
      const updatedOutcomes = market.outcomes.map((outcome) => {
        const tokenPrice = priceUpdate.tokens.find(
          (t) => t.tokenId === outcome.tokenId || t.outcome.toLowerCase() === outcome.outcomeName.toLowerCase()
        );
        if (tokenPrice) {
          return {
            ...outcome,
            currentPrice: tokenPrice.price,
          };
        }
        return outcome;
      });

      return {
        ...market,
        outcomes: updatedOutcomes,
        volume24h: priceUpdate.volume24h ?? market.volume24h,
        liquidity: priceUpdate.liquidity ?? market.liquidity,
      };
    });
  }, [markets, realtimePriceData, realtimePrices?.enabled]);

  // Sync URL hash with expanded state
  useEffect(() => {
    if (!persistToUrl || typeof window === 'undefined') return;

    const newHash = marketIdsToHash(expandedIds);
    const currentHash = window.location.hash.slice(1);

    if (newHash !== currentHash) {
      // Use replaceState to avoid polluting history
      const url = new URL(window.location.href);
      url.hash = newHash;
      window.history.replaceState(null, '', url.toString());
    }
  }, [expandedIds, persistToUrl]);

  // Listen for hash changes (back/forward navigation)
  useEffect(() => {
    if (!persistToUrl || typeof window === 'undefined') return;

    const handleHashChange = () => {
      const hashIds = parseHashToMarketIds();
      const newIds = mode === 'single' ? hashIds.slice(0, 1) : hashIds;
      setExpandedIds(newIds);
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [persistToUrl, mode]);

  // Handle accordion value change
  const handleValueChange = useCallback(
    (value: string | string[]) => {
      const newIds = Array.isArray(value) ? value : value ? [value] : [];
      setExpandedIds(newIds);
      onExpandChange?.(newIds);
    },
    [onExpandChange]
  );

  // Empty state
  if (!markets || markets.length === 0) {
    return (
      <div className={cn('rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500', className)}>
        No markets found for this event.
      </div>
    );
  }

  // Render based on mode
  if (mode === 'single') {
    return (
      <Accordion.Root
        type="single"
        value={expandedIds[0] || ''}
        onValueChange={(value) => handleValueChange(value)}
        collapsible
        className={cn('space-y-2', className)}
      >
        {marketsWithRealtimePrices.map((market) => (
          <MarketAccordionItem
            key={market.id}
            market={market}
            onTradeClick={onTradeClick}
            pricesLastUpdated={realtimePrices?.enabled ? pricesLastUpdated : undefined}
          />
        ))}
      </Accordion.Root>
    );
  }

  // Multiple mode
  return (
    <Accordion.Root
      type="multiple"
      value={expandedIds}
      onValueChange={(value) => handleValueChange(value)}
      className={cn('space-y-2', className)}
    >
      {marketsWithRealtimePrices.map((market) => (
        <MarketAccordionItem
          key={market.id}
          market={market}
          onTradeClick={onTradeClick}
          pricesLastUpdated={realtimePrices?.enabled ? pricesLastUpdated : undefined}
        />
      ))}
    </Accordion.Root>
  );
}

interface MarketAccordionItemProps {
  market: AccordionMarket;
  onTradeClick?: (selection: TradeSelection) => void;
  /** Last price update timestamp for real-time updates */
  pricesLastUpdated?: number | null;
}

/**
 * MarketAccordionHeader - Enhanced header component for collapsed row display
 *
 * PRD: market_accordion_header
 *
 * Features:
 * - Display market name/candidate name prominently
 * - Show current probability as large percentage with color coding
 * - Display bid/ask spread inline
 * - Show 24h volume and price change indicators
 * - Chevron icon that rotates on expand
 * - Small profile image/avatar for candidate markets
 * - Hover state with subtle background change
 */
interface MarketAccordionHeaderProps {
  market: AccordionMarket;
  primaryOutcome: MarketOutcome | null;
  /** All outcomes for the market (for buy buttons) */
  allOutcomes: MarketOutcome[];
  /** Callback when buy button is clicked */
  onTradeClick?: (selection: TradeSelection) => void;
  /** Last price update timestamp for real-time display */
  pricesLastUpdated?: number | null;
}

const MarketAccordionHeader = memo(function MarketAccordionHeader({
  market,
  primaryOutcome,
  allOutcomes,
  onTradeClick,
  pricesLastUpdated,
}: MarketAccordionHeaderProps) {
  // Track previous price for flash animation
  const prevPrice = usePreviousValue(primaryOutcome?.currentPrice);

  // Format bid/ask spread for display
  const bidAskSpread =
    primaryOutcome?.bestBid !== undefined && primaryOutcome?.bestAsk !== undefined
      ? `${Math.round(primaryOutcome.bestBid * 100)}¢ / ${Math.round(primaryOutcome.bestAsk * 100)}¢`
      : null;

  // Find Yes and No outcomes for buy buttons
  const yesOutcome = allOutcomes.find(
    (o) => o.outcomeName.toLowerCase() === 'yes'
  );
  const noOutcome = allOutcomes.find(
    (o) => o.outcomeName.toLowerCase() === 'no'
  );

  // Determine if trading is available
  const isTradingDisabled = market.isResolved === true;

  // Handle buy button click
  const handleBuyClick = useCallback(
    (e: React.MouseEvent, outcome: MarketOutcome) => {
      e.stopPropagation(); // Prevent accordion toggle
      e.preventDefault();

      if (isTradingDisabled || !onTradeClick) return;

      onTradeClick({
        marketId: market.id,
        outcomeId: outcome.id,
        tokenId: outcome.tokenId,
        outcomeName: outcome.outcomeName,
        currentPrice: outcome.currentPrice,
        direction: 'buy',
      });
    },
    [market.id, isTradingDisabled, onTradeClick]
  );

  return (
    <Accordion.Trigger className={cn(
      'group flex w-full text-left transition-colors',
      'hover:bg-gray-50/80 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500',
      'data-[state=open]:bg-gray-50/50',
      // Mobile: Stack vertically with reduced padding
      'flex-col items-stretch p-3 gap-2',
      // Desktop: Horizontal layout with full padding
      'sm:flex-row sm:items-center sm:justify-between sm:p-4 sm:gap-0'
    )}>
      {/* Top section: Avatar, question, and probability (mobile) / Left side (desktop) */}
      <div className="flex flex-1 items-center gap-2 sm:gap-3 min-w-0 sm:pr-4">
        {/* Optional avatar/image for candidate markets */}
        {market.imageUrl && (
          <div className="flex-shrink-0">
            <img
              src={market.imageUrl}
              alt=""
              className={cn(
                'rounded-full object-cover ring-2 ring-gray-100',
                // Mobile: Smaller avatar
                'h-8 w-8',
                // Desktop: Full-size avatar
                'sm:h-10 sm:w-10'
              )}
            />
          </div>
        )}

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Market Question / Candidate Name */}
          <h3 className={cn(
            'font-semibold text-gray-900 truncate',
            // Mobile: Smaller text
            'text-sm',
            // Desktop: Normal text
            'sm:text-base'
          )}>
            {market.question}
          </h3>

          {/* Secondary info row: volume, bid/ask, liquidity - hidden on mobile */}
          <div className="hidden sm:flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs text-gray-500">
            {market.volume24h !== undefined && market.volume24h > 0 && (
              <span className="inline-flex items-center gap-1">
                <span className="text-gray-400">24h Vol:</span>
                <span className="font-medium text-gray-600">${formatVolume(market.volume24h)}</span>
              </span>
            )}
            {bidAskSpread && (
              <span className="inline-flex items-center gap-1">
                <span className="text-gray-400">Bid/Ask:</span>
                <span className="font-medium text-gray-600">{bidAskSpread}</span>
              </span>
            )}
            {market.liquidity > 0 && (
              <span className="inline-flex items-center gap-1">
                <span className="text-gray-400">Liq:</span>
                <span className="font-medium text-gray-600">${formatVolume(market.liquidity)}</span>
              </span>
            )}
          </div>
        </div>

        {/* Mobile: Probability + chevron in top row */}
        <div className="flex items-center gap-2 sm:hidden flex-shrink-0">
          {primaryOutcome && (
            <AnimatedPriceDisplay
              price={primaryOutcome.currentPrice}
              previousPrice={prevPrice}
              lastUpdated={pricesLastUpdated}
              size="sm"
            />
          )}
          <ChevronDown
            className={cn(
              'h-5 w-5 text-gray-400 transition-transform duration-200 flex-shrink-0',
              'group-data-[state=open]:rotate-180'
            )}
            aria-hidden="true"
          />
        </div>
      </div>

      {/* Mobile: Secondary info row with price change and volume */}
      <div className="flex items-center justify-between gap-2 sm:hidden text-xs text-gray-500">
        <div className="flex items-center gap-3">
          {primaryOutcome?.priceChange24h !== undefined && primaryOutcome.priceChange24h !== 0 && (
            <PriceChangeIndicator change={primaryOutcome.priceChange24h} size="sm" />
          )}
          {market.volume24h !== undefined && market.volume24h > 0 && (
            <span className="text-gray-500">
              Vol: ${formatVolume(market.volume24h)}
            </span>
          )}
        </div>
        {/* Mobile buy buttons */}
        {yesOutcome && noOutcome && (
          <div className="flex items-center gap-1">
            <BuyButton
              outcome={yesOutcome}
              variant="yes"
              disabled={isTradingDisabled}
              onClick={(e) => handleBuyClick(e, yesOutcome)}
              size="sm"
            />
            <BuyButton
              outcome={noOutcome}
              variant="no"
              disabled={isTradingDisabled}
              onClick={(e) => handleBuyClick(e, noOutcome)}
              size="sm"
            />
          </div>
        )}
      </div>

      {/* Desktop: Right side with Buy buttons, Price display and indicators */}
      <div className="hidden sm:flex items-center gap-2 sm:gap-3 flex-shrink-0">
        {/* Buy Yes/No buttons - only show for binary markets with Yes/No outcomes */}
        {yesOutcome && noOutcome && (
          <div className="flex items-center gap-1.5">
            <BuyButton
              outcome={yesOutcome}
              variant="yes"
              disabled={isTradingDisabled}
              onClick={(e) => handleBuyClick(e, yesOutcome)}
            />
            <BuyButton
              outcome={noOutcome}
              variant="no"
              disabled={isTradingDisabled}
              onClick={(e) => handleBuyClick(e, noOutcome)}
            />
          </div>
        )}

        {primaryOutcome && (
          <>
            {/* 24h price change indicator */}
            {primaryOutcome.priceChange24h !== undefined && primaryOutcome.priceChange24h !== 0 && (
              <PriceChangeIndicator change={primaryOutcome.priceChange24h} />
            )}

            {/* Large probability display with color coding and flash animation */}
            <AnimatedPriceDisplay
              price={primaryOutcome.currentPrice}
              previousPrice={prevPrice}
              lastUpdated={pricesLastUpdated}
            />
          </>
        )}

        {/* Chevron indicator with rotation animation */}
        <ChevronDown
          className={cn(
            'h-5 w-5 text-gray-400 transition-transform duration-200 flex-shrink-0',
            'group-data-[state=open]:rotate-180'
          )}
          aria-hidden="true"
        />
      </div>
    </Accordion.Trigger>
  );
});

/**
 * BuyButton - Compact buy button for Yes/No outcomes
 *
 * PRD: buy_buttons_inline
 *
 * Features:
 * - Compact pill button style (green for Yes, red for No)
 * - Shows current price on button (e.g., "Yes 95¢")
 * - Clicking opens trading panel with outcome pre-selected
 * - Disabled when market is resolved or trading is paused
 * - Hover tooltip shows estimated cost for 100 shares
 * - Supports 'sm' size for mobile (reduced padding, min touch target 44px)
 */
interface BuyButtonProps {
  outcome: MarketOutcome;
  variant: 'yes' | 'no';
  disabled: boolean;
  onClick: (e: React.MouseEvent) => void;
  /** Size variant for responsive layouts */
  size?: 'sm' | 'default';
}

const BuyButton = memo(function BuyButton({
  outcome,
  variant,
  disabled,
  onClick,
  size = 'default',
}: BuyButtonProps) {
  const priceInCents = Math.round(outcome.currentPrice * 100);
  const estimatedCost = (100 * outcome.currentPrice).toFixed(2);

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={disabled ? 'Trading unavailable' : `Buy 100 shares for $${estimatedCost}`}
      className={cn(
        'inline-flex items-center rounded-full font-semibold',
        'transition-all duration-150 whitespace-nowrap',
        'focus:outline-none focus:ring-2 focus:ring-offset-1',
        // Size variants - ensure min 44px touch target on mobile
        size === 'sm'
          ? 'gap-0.5 px-2 py-1.5 text-[11px] min-h-[32px]'
          : 'gap-1 px-2.5 py-1 text-xs',
        variant === 'yes'
          ? disabled
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-green-100 text-green-700 hover:bg-green-200 focus:ring-green-500 hover:shadow-sm active:bg-green-300'
          : disabled
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-red-100 text-red-700 hover:bg-red-200 focus:ring-red-500 hover:shadow-sm active:bg-red-300'
      )}
    >
      <span>{size === 'sm' ? variant.charAt(0).toUpperCase() : outcome.outcomeName}</span>
      <span className="tabular-nums">{priceInCents}¢</span>
    </button>
  );
});

/**
 * PriceChangeIndicator - Shows 24h price change with trend icon
 *
 * PRD: accordion_mobile_responsive
 *
 * Supports 'sm' size for mobile layouts with reduced padding.
 */
interface PriceChangeIndicatorProps {
  /** Change value (absolute, e.g., 0.05 for 5%) */
  change: number;
  /** Size variant for responsive layouts */
  size?: 'sm' | 'default';
}

const PriceChangeIndicator = memo(function PriceChangeIndicator({
  change,
  size = 'default',
}: PriceChangeIndicatorProps) {
  const isPositive = change > 0;
  const absChange = Math.abs(change * 100);
  const Icon = isPositive ? TrendingUp : TrendingDown;

  return (
    <div
      className={cn(
        'flex items-center font-medium rounded-md',
        size === 'sm'
          ? 'gap-0.5 text-[11px] px-1.5 py-0.5'
          : 'gap-1 text-xs px-2 py-1',
        isPositive ? 'text-green-700 bg-green-50' : 'text-red-700 bg-red-50'
      )}
      title={`24h change: ${isPositive ? '+' : '-'}${absChange.toFixed(1)}%`}
    >
      <Icon className={size === 'sm' ? 'h-2.5 w-2.5' : 'h-3 w-3'} />
      <span>{absChange.toFixed(1)}%</span>
    </div>
  );
});

/**
 * AnimatedPriceDisplay - Shows probability with flash animation on price changes
 *
 * PRD: realtime_price_updates
 *
 * Features:
 * - Displays probability as large percentage with color coding
 * - Flashes green/red briefly when price increases/decreases
 * - Shows last update timestamp on hover
 */
interface AnimatedPriceDisplayProps {
  /** Current price (0.0 to 1.0) */
  price: number;
  /** Previous price for detecting changes (0.0 to 1.0) */
  previousPrice?: number;
  /** Last update timestamp */
  lastUpdated?: number | null;
  /** Size variant */
  size?: 'sm' | 'default';
}

const AnimatedPriceDisplay = memo(function AnimatedPriceDisplay({
  price,
  previousPrice,
  lastUpdated,
  size = 'default',
}: AnimatedPriceDisplayProps) {
  const colors = getProbabilityColor(price);
  const [flashDirection, setFlashDirection] = useState<'up' | 'down' | null>(null);
  const prevPriceRef = useRef<number | undefined>(previousPrice);

  // Detect price changes and trigger flash animation
  useEffect(() => {
    const prev = prevPriceRef.current;
    if (prev !== undefined && prev !== price) {
      // Only flash if change is significant (> 0.1%)
      const change = price - prev;
      if (Math.abs(change) >= 0.001) {
        setFlashDirection(change > 0 ? 'up' : 'down');
        // Clear flash after animation completes
        const timer = setTimeout(() => setFlashDirection(null), 1000);
        return () => clearTimeout(timer);
      }
    }
    prevPriceRef.current = price;
  }, [price]);

  // Format last updated timestamp
  const formattedLastUpdated = useMemo(() => {
    if (!lastUpdated) return null;
    const date = new Date(lastUpdated);
    return `Last updated: ${date.toLocaleTimeString()}`;
  }, [lastUpdated]);

  return (
    <div
      className={cn(
        'flex items-baseline gap-1 rounded-lg transition-colors',
        size === 'sm' ? 'px-2 py-1' : 'px-3 py-1.5',
        colors.bg,
        flashDirection === 'up' && 'animate-[price-flash-up_1s_ease-out]',
        flashDirection === 'down' && 'animate-[price-flash-down_1s_ease-out]'
      )}
      title={formattedLastUpdated || undefined}
    >
      <span className={cn(
        'font-bold tabular-nums',
        size === 'sm' ? 'text-lg' : 'text-2xl',
        colors.text
      )}>
        {formatProbability(price)}
      </span>
      {size !== 'sm' && (
        <span className={cn('text-xs font-medium opacity-70', colors.text)}>
          {formatProbabilityAsCents(price)}
        </span>
      )}
    </div>
  );
});

/**
 * Hook to track previous values for price change detection
 */
function usePreviousValue<T>(value: T): T | undefined {
  const ref = useRef<T | undefined>(undefined);
  useEffect(() => {
    ref.current = value;
  }, [value]);
  return ref.current;
}

/**
 * MarketAccordionContent - Expandable content panel with tabs
 *
 * PRD: market_accordion_content
 *
 * Features:
 * - Tabbed interface with Order Book, Graph, and Resolution tabs
 * - Local state for active tab (within each accordion item)
 * - Smooth fade-in animation when content appears
 * - Lazy load tab content to minimize API calls for collapsed markets
 * - Loading skeleton while tab content is fetching
 */
interface MarketAccordionContentProps {
  market: AccordionMarket;
  primaryOutcome: MarketOutcome | null;
}

interface TabConfig {
  value: AccordionTabValue;
  label: string;
  icon: React.ReactNode;
}

const ACCORDION_TABS: TabConfig[] = [
  { value: 'orderbook', label: 'Order Book', icon: <BookOpen className="h-4 w-4" /> },
  { value: 'graph', label: 'Graph', icon: <LineChart className="h-4 w-4" /> },
  { value: 'resolution', label: 'Resolution', icon: <FileText className="h-4 w-4" /> },
];

const MarketAccordionContent = memo(function MarketAccordionContent({
  market,
  primaryOutcome,
}: MarketAccordionContentProps) {
  const [activeTab, setActiveTab] = useState<AccordionTabValue>('orderbook');
  const [timeRange, setTimeRange] = useState<TimeRange>(DEFAULT_TIME_RANGE);
  const [isTimeseriesLoading, setIsTimeseriesLoading] = useState(false);

  // Get the primary token ID for Order Book and Graph
  const primaryTokenId = primaryOutcome?.tokenId;
  const interval = TIME_RANGE_TO_INTERVAL[timeRange];

  // Handle time range change with loading state
  const handleTimeRangeChange = useCallback((range: TimeRange) => {
    setIsTimeseriesLoading(true);
    setTimeRange(range);
    // Reset loading state after a short delay (data fetch will update it)
    setTimeout(() => setIsTimeseriesLoading(false), 100);
  }, []);

  return (
    <div className="animate-in fade-in duration-200">
      <Tabs.Root value={activeTab} onValueChange={(v) => setActiveTab(v as AccordionTabValue)}>
        {/* Tab List - scrollable on mobile */}
        <div className="border-b border-gray-200 bg-white rounded-t-lg overflow-hidden">
          <Tabs.List
            className={cn(
              'flex overflow-x-auto',
              // Hide scrollbar but allow scrolling
              'scrollbar-hide',
              // Ensure tabs don't wrap on mobile
              '-mx-px'
            )}
            aria-label="Market details tabs"
          >
            {ACCORDION_TABS.map((tab) => (
              <Tabs.Trigger
                key={tab.value}
                value={tab.value}
                className={cn(
                  'flex items-center gap-1.5 font-medium whitespace-nowrap',
                  'border-b-2 transition-colors duration-200',
                  'hover:text-gray-900 hover:bg-gray-50',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2',
                  'data-[state=active]:border-indigo-600 data-[state=active]:text-indigo-600',
                  'data-[state=inactive]:border-transparent data-[state=inactive]:text-gray-500',
                  // Mobile: Smaller padding, ensure 44px min touch target height
                  'px-3 py-3 text-xs min-h-[44px]',
                  // Desktop: Larger padding
                  'sm:px-4 sm:py-2.5 sm:text-sm sm:gap-2'
                )}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </div>

        {/* Tab Content - reduced padding on mobile */}
        <div className="p-3 sm:p-4 bg-white rounded-b-lg">
          {/* Order Book Tab */}
          <Tabs.Content
            value="orderbook"
            className="focus:outline-none data-[state=inactive]:hidden animate-in fade-in duration-150"
          >
            <OrderBookTabContent tokenId={primaryTokenId} />
          </Tabs.Content>

          {/* Graph Tab */}
          <Tabs.Content
            value="graph"
            className="focus:outline-none data-[state=inactive]:hidden animate-in fade-in duration-150"
          >
            <GraphTabContent
              tokenId={primaryTokenId}
              timeRange={timeRange}
              interval={interval}
              isLoading={isTimeseriesLoading}
              onTimeRangeChange={handleTimeRangeChange}
              outcomeName={primaryOutcome?.outcomeName}
            />
          </Tabs.Content>

          {/* Resolution Tab */}
          <Tabs.Content
            value="resolution"
            className="focus:outline-none data-[state=inactive]:hidden animate-in fade-in duration-150"
          >
            <ResolutionTabContent market={market} />
          </Tabs.Content>
        </div>
      </Tabs.Root>
    </div>
  );
});

/**
 * OrderBookTabContent - Lazy-loaded Order Book tab wrapper with refresh capability
 *
 * PRD: orderbook_tab_integration
 *
 * Features:
 * - Wraps OrderBook component with proper sizing for accordion context
 * - Shows loading skeleton while data is loading
 * - Handles orderbook unavailable gracefully (show message, not error)
 * - Provides refresh button for manual orderbook update
 */
interface OrderBookTabContentProps {
  tokenId: string | undefined;
}

const OrderBookTabContent = memo(function OrderBookTabContent({
  tokenId,
}: OrderBookTabContentProps) {
  const [isManualRefreshing, setIsManualRefreshing] = useState(false);

  // Handle manual refresh
  const handleRefresh = useCallback(async (refetchFn: () => Promise<unknown>) => {
    setIsManualRefreshing(true);
    try {
      await refetchFn();
    } finally {
      // Reset after a short delay to show the animation
      setTimeout(() => setIsManualRefreshing(false), 500);
    }
  }, []);

  if (!tokenId) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-gray-500">
        Select an outcome to view the order book
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <OrderBookWithRefresh
        tokenId={tokenId}
        isManualRefreshing={isManualRefreshing}
        onRefresh={handleRefresh}
      />
    </div>
  );
});

/**
 * OrderBookWithRefresh - OrderBook wrapper with refresh button
 *
 * Separated component to use the useOrderbook hook directly
 * and provide the refresh button functionality.
 */
interface OrderBookWithRefreshProps {
  tokenId: string;
  isManualRefreshing: boolean;
  onRefresh: (refetchFn: () => Promise<unknown>) => void;
}

const OrderBookWithRefresh = memo(function OrderBookWithRefresh({
  tokenId,
  isManualRefreshing,
  onRefresh,
}: OrderBookWithRefreshProps) {
  const {
    data,
    isLoading,
    error,
    refetch,
    dataUpdatedAt,
    isFetching,
  } = useOrderbook(tokenId, { depth: 5, refetchInterval: 5000, enabled: !!tokenId });

  // Format last updated time
  const lastUpdatedText = useMemo(() => {
    if (!dataUpdatedAt) return null;
    const date = new Date(dataUpdatedAt);
    return date.toLocaleTimeString();
  }, [dataUpdatedAt]);

  // Handle error state with graceful message
  if (error && !data) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-6">
        <div className="flex flex-col items-center justify-center text-center gap-3">
          <AlertCircle className="h-8 w-8 text-gray-400" />
          <div className="space-y-1">
            <p className="text-sm font-medium text-gray-700">Order book unavailable</p>
            <p className="text-xs text-gray-500">
              {error instanceof Error ? error.message : 'Unable to load order book data'}
            </p>
          </div>
          <button
            onClick={() => onRefresh(refetch)}
            disabled={isFetching}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium',
              'text-gray-700 bg-white border border-gray-300 rounded-md',
              'hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
              'transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <RefreshCw className={cn('h-3 w-3', isFetching && 'animate-spin')} />
            Try again
          </button>
        </div>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return <OrderBookSkeleton levels={5} className="border-0 shadow-none" />;
  }

  // Empty state
  if (!data || (data.bids.length === 0 && data.asks.length === 0)) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 flex flex-col items-center justify-center text-center gap-2">
        <BookOpen className="h-8 w-8 text-gray-300" />
        <p className="text-sm text-gray-500">No orders available</p>
        <button
          onClick={() => onRefresh(refetch)}
          disabled={isFetching}
          className={cn(
            'inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700',
            'focus:outline-none disabled:opacity-50'
          )}
        >
          <RefreshCw className={cn('h-3 w-3', isFetching && 'animate-spin')} />
          Refresh
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Refresh button in header area */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {lastUpdatedText && (
            <span>Updated {lastUpdatedText}</span>
          )}
          {isFetching && !isManualRefreshing && (
            <span className="text-indigo-500">Updating...</span>
          )}
        </div>
        <button
          onClick={() => onRefresh(refetch)}
          disabled={isFetching}
          title="Refresh order book"
          className={cn(
            'inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium rounded-md',
            'text-gray-600 hover:text-gray-900 hover:bg-gray-100',
            'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
            'transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
            isManualRefreshing && 'bg-indigo-50 text-indigo-600'
          )}
        >
          <RefreshCw className={cn('h-3.5 w-3.5', (isManualRefreshing || isFetching) && 'animate-spin')} />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      {/* Order book component */}
      <OrderBook tokenId={tokenId} levels={5} className="border-0 shadow-none" />
    </div>
  );
});

/**
 * GraphTabContent - Lazy-loaded Graph tab wrapper with time range selector
 */
interface GraphTabContentProps {
  tokenId: string | undefined;
  timeRange: TimeRange;
  interval: string;
  isLoading: boolean;
  onTimeRangeChange: (range: TimeRange) => void;
  outcomeName?: string;
}

const GraphTabContent = memo(function GraphTabContent({
  tokenId,
  timeRange,
  interval,
  isLoading,
  onTimeRangeChange,
  outcomeName,
}: GraphTabContentProps) {
  if (!tokenId) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-gray-500">
        Select an outcome to view price history
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Time Range Selector */}
      <div className="flex justify-end">
        <TimeRangeSelector
          value={timeRange}
          onChange={onTimeRangeChange}
          isLoading={isLoading}
          persistInUrl={false}
        />
      </div>

      {/* Price Chart */}
      <PriceChart
        tokenId={tokenId}
        interval={interval as import('@/hooks').TimeseriesInterval}
        height={250}
        outcomeName={outcomeName}
        showMidLine
      />
    </div>
  );
});

/**
 * ResolutionTabContent - Resolution rules display
 */
interface ResolutionTabContentProps {
  market: AccordionMarket;
}

const ResolutionTabContent = memo(function ResolutionTabContent({
  market,
}: ResolutionTabContentProps) {
  return (
    <div className="max-w-2xl mx-auto">
      <ResolutionRules
        description={market.description}
        resolverType={market.resolverType}
        resolutionSource={market.resolutionSource}
        isResolved={market.isResolved}
        resolutionOutcome={market.resolutionOutcome}
        className="border-0 shadow-none"
      />
    </div>
  );
});

/**
 * Individual accordion item for a market
 */
const MarketAccordionItem = memo(function MarketAccordionItem({
  market,
  onTradeClick,
  pricesLastUpdated,
}: MarketAccordionItemProps) {
  // Get the primary outcome (highest probability) for header display
  const primaryOutcome = market.outcomes.length > 0
    ? market.outcomes.reduce<MarketOutcome>(
        (max, outcome) => (outcome.currentPrice > max.currentPrice ? outcome : max),
        market.outcomes[0]!
      )
    : null;

  return (
    <Accordion.Item
      value={market.id}
      className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm hover:shadow-md transition-shadow"
    >
      <Accordion.Header className="flex">
        <MarketAccordionHeader
          market={market}
          primaryOutcome={primaryOutcome}
          allOutcomes={market.outcomes}
          onTradeClick={onTradeClick}
          pricesLastUpdated={pricesLastUpdated}
        />
      </Accordion.Header>

      <Accordion.Content className="overflow-hidden data-[state=open]:animate-accordion-down data-[state=closed]:animate-accordion-up">
        <div className="border-t border-gray-100 bg-gray-50/30">
          <MarketAccordionContent market={market} primaryOutcome={primaryOutcome} />
        </div>
      </Accordion.Content>
    </Accordion.Item>
  );
});

/**
 * Format volume for display
 */
function formatVolume(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toFixed(2);
}

// ============================================================================
// Loading States Components
// PRD: accordion_loading_states
// ============================================================================

/**
 * Props for MarketAccordionSkeleton
 */
export interface MarketAccordionSkeletonProps {
  /** Number of skeleton rows to display */
  rows?: number;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Skeleton block with shimmer animation
 */
function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 animate-shimmer bg-[length:200%_100%] rounded',
        className
      )}
    />
  );
}

/**
 * MarketAccordionSkeleton - Loading skeleton for market accordion
 *
 * PRD: accordion_loading_states
 *
 * Displays skeleton rows with animated placeholders matching the accordion structure.
 * Maintains layout dimensions to prevent layout shift during loading.
 *
 * @example
 * ```tsx
 * if (isLoading) {
 *   return <MarketAccordionSkeleton rows={3} />;
 * }
 * ```
 */
export function MarketAccordionSkeleton({
  rows = 3,
  className,
}: MarketAccordionSkeletonProps) {
  return (
    <div className={cn('space-y-2', className)} data-testid="market-accordion-skeleton">
      {Array.from({ length: rows }).map((_, index) => (
        <MarketAccordionRowSkeleton key={index} index={index} />
      ))}
    </div>
  );
}

/**
 * Single row skeleton for the market accordion
 */
interface MarketAccordionRowSkeletonProps {
  index?: number;
}

const MarketAccordionRowSkeleton = memo(function MarketAccordionRowSkeleton({
  index = 0,
}: MarketAccordionRowSkeletonProps) {
  return (
    <div
      className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm"
      style={{ animationDelay: `${index * 100}ms` }}
      data-testid="market-accordion-row-skeleton"
    >
      {/* Mobile layout */}
      <div className="sm:hidden">
        <div className="flex flex-col gap-2 p-3">
          {/* Top row: avatar, question, probability, chevron */}
          <div className="flex items-center gap-2">
            <SkeletonBlock className="h-8 w-8 rounded-full flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <SkeletonBlock className="h-4 w-3/4" />
            </div>
            <SkeletonBlock className="h-8 w-14 rounded-lg" />
            <SkeletonBlock className="h-5 w-5" />
          </div>
          {/* Bottom row: price change, volume, buy buttons */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <SkeletonBlock className="h-5 w-12 rounded-md" />
              <SkeletonBlock className="h-4 w-16" />
            </div>
            <div className="flex items-center gap-1">
              <SkeletonBlock className="h-7 w-10 rounded-full" />
              <SkeletonBlock className="h-7 w-10 rounded-full" />
            </div>
          </div>
        </div>
      </div>

      {/* Desktop layout */}
      <div className="hidden sm:block">
        <div className="flex w-full items-center justify-between p-4">
          {/* Left side: avatar + content */}
          <div className="flex flex-1 items-center gap-3 min-w-0 pr-4">
            {/* Avatar placeholder */}
            <SkeletonBlock className="h-10 w-10 rounded-full flex-shrink-0" />

            {/* Main content */}
            <div className="flex-1 min-w-0 space-y-2">
              {/* Market question */}
              <SkeletonBlock className="h-5 w-3/4" />

              {/* Secondary info row */}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <SkeletonBlock className="h-3 w-16" />
                <SkeletonBlock className="h-3 w-20" />
                <SkeletonBlock className="h-3 w-14" />
              </div>
            </div>
          </div>

          {/* Right side: buy buttons, probability, chevron */}
          <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
            {/* Buy buttons */}
            <div className="flex items-center gap-1.5">
              <SkeletonBlock className="h-7 w-16 rounded-full" />
              <SkeletonBlock className="h-7 w-14 rounded-full" />
            </div>

            {/* Price change indicator */}
            <SkeletonBlock className="h-6 w-14 rounded-md" />

            {/* Probability badge */}
            <SkeletonBlock className="h-10 w-20 rounded-lg" />

            {/* Chevron */}
            <SkeletonBlock className="h-5 w-5" />
          </div>
        </div>
      </div>
    </div>
  );
});

/**
 * Props for MarketAccordionError
 */
export interface MarketAccordionErrorProps {
  /** Error message to display */
  error: string;
  /** Callback when retry button is clicked */
  onRetry?: () => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * MarketAccordionError - Error state with retry option
 *
 * PRD: accordion_loading_states
 *
 * Displays an error message and optional retry button when market data fails to load.
 * Maintains the accordion structure to prevent layout shift.
 *
 * @example
 * ```tsx
 * if (error) {
 *   return (
 *     <MarketAccordionError
 *       error={error.message}
 *       onRetry={() => refetch()}
 *     />
 *   );
 * }
 * ```
 */
export function MarketAccordionError({
  error,
  onRetry,
  className,
}: MarketAccordionErrorProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-red-200 bg-red-50 p-6',
        className
      )}
      data-testid="market-accordion-error"
    >
      <div className="flex flex-col items-center justify-center gap-3 text-center">
        <div className="flex items-center justify-center h-10 w-10 rounded-full bg-red-100">
          <AlertCircle className="h-5 w-5 text-red-600" />
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-red-800">
            Failed to load markets
          </h3>
          <p className="text-sm text-red-600">{error}</p>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className={cn(
              'inline-flex items-center gap-2 px-4 py-2 text-sm font-medium',
              'text-red-700 bg-white border border-red-300 rounded-lg',
              'hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2',
              'transition-colors'
            )}
          >
            <RefreshCw className="h-4 w-4" />
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Props for MarketAccordionItemError
 */
export interface MarketAccordionItemErrorProps {
  /** Market ID that failed to load */
  marketId: string;
  /** Error message */
  error: string;
  /** Callback when retry button is clicked */
  onRetry?: (marketId: string) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * MarketAccordionItemError - Error state for a single market item
 *
 * PRD: accordion_loading_states
 *
 * Displays an error state for a single market that failed to load,
 * while other markets may still be visible. Useful for partial loading failures.
 *
 * @example
 * ```tsx
 * {markets.map((market) => (
 *   market.error ? (
 *     <MarketAccordionItemError
 *       key={market.id}
 *       marketId={market.id}
 *       error={market.error.message}
 *       onRetry={(id) => refetchMarket(id)}
 *     />
 *   ) : (
 *     <MarketAccordionItem key={market.id} market={market} />
 *   )
 * ))}
 * ```
 */
export function MarketAccordionItemError({
  marketId,
  error,
  onRetry,
  className,
}: MarketAccordionItemErrorProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-red-200 bg-white overflow-hidden shadow-sm',
        className
      )}
      data-testid="market-accordion-item-error"
    >
      <div className="flex items-center justify-between p-4 bg-red-50/50">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center justify-center h-8 w-8 rounded-full bg-red-100 flex-shrink-0">
            <AlertCircle className="h-4 w-4 text-red-600" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-red-800 truncate">
              Failed to load market
            </p>
            <p className="text-xs text-red-600 truncate">{error}</p>
          </div>
        </div>
        {onRetry && (
          <button
            onClick={() => onRetry(marketId)}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium',
              'text-red-700 bg-white border border-red-300 rounded-md',
              'hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1',
              'transition-colors flex-shrink-0'
            )}
          >
            <RefreshCw className="h-3 w-3" />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Props for MarketAccordionLoading
 */
export interface MarketAccordionLoadingProps {
  /** Markets that have loaded successfully */
  markets: AccordionMarket[];
  /** Market IDs that are still loading */
  loadingMarketIds?: string[];
  /** Market IDs that failed with their error messages */
  failedMarkets?: Array<{ id: string; error: string }>;
  /** Callback when retry is clicked for a failed market */
  onRetryMarket?: (marketId: string) => void;
  /** Expansion mode: 'single' allows one open, 'multiple' allows many */
  mode?: AccordionMode;
  /** Default expanded market ID(s) */
  defaultExpanded?: string | string[];
  /** Callback when expansion changes */
  onExpandChange?: (expandedIds: string[]) => void;
  /** Callback when a buy button is clicked */
  onTradeClick?: (selection: TradeSelection) => void;
  /** Whether to sync expanded state with URL hash */
  persistToUrl?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * MarketAccordionLoading - Handles partial loading states
 *
 * PRD: accordion_loading_states
 *
 * Renders loaded markets alongside skeleton placeholders for markets still loading,
 * and error states for markets that failed. This allows displaying partial data
 * while additional markets are being fetched.
 *
 * @example
 * ```tsx
 * <MarketAccordionLoading
 *   markets={loadedMarkets}
 *   loadingMarketIds={['market-4', 'market-5']}
 *   failedMarkets={[{ id: 'market-6', error: 'Network error' }]}
 *   onRetryMarket={(id) => refetchMarket(id)}
 * />
 * ```
 */
export function MarketAccordionLoading({
  markets,
  loadingMarketIds = [],
  failedMarkets = [],
  onRetryMarket,
  mode = 'single',
  defaultExpanded,
  onExpandChange,
  onTradeClick,
  persistToUrl = true,
  className,
}: MarketAccordionLoadingProps) {
  // If there are no loaded markets and we have loading/failed states, show appropriate UI
  if (markets.length === 0 && loadingMarketIds.length === 0 && failedMarkets.length === 0) {
    return (
      <div className={cn('rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500', className)}>
        No markets found for this event.
      </div>
    );
  }

  // If everything is still loading, show full skeleton
  if (markets.length === 0 && loadingMarketIds.length > 0 && failedMarkets.length === 0) {
    return <MarketAccordionSkeleton rows={loadingMarketIds.length} className={className} />;
  }

  // If everything failed, show error state
  if (markets.length === 0 && loadingMarketIds.length === 0 && failedMarkets.length > 0) {
    return (
      <MarketAccordionError
        error={failedMarkets[0]?.error || 'Failed to load markets'}
        onRetry={onRetryMarket ? () => onRetryMarket(failedMarkets[0]?.id || '') : undefined}
        className={className}
      />
    );
  }

  return (
    <div className={cn('space-y-2', className)}>
      {/* Render loaded markets */}
      {markets.length > 0 && (
        <MarketAccordion
          markets={markets}
          mode={mode}
          defaultExpanded={defaultExpanded}
          onExpandChange={onExpandChange}
          onTradeClick={onTradeClick}
          persistToUrl={persistToUrl}
        />
      )}

      {/* Render loading skeletons for pending markets */}
      {loadingMarketIds.length > 0 && (
        <MarketAccordionSkeleton rows={loadingMarketIds.length} />
      )}

      {/* Render error states for failed markets */}
      {failedMarkets.map((failed) => (
        <MarketAccordionItemError
          key={failed.id}
          marketId={failed.id}
          error={failed.error}
          onRetry={onRetryMarket}
        />
      ))}
    </div>
  );
}

// ============================================================================
// Multi-Market Layout Components
// PRD: multi_market_layout
// ============================================================================

/**
 * Sort options for multi-market layout
 */
export type MarketSortOption = 'probability' | 'volume' | 'alphabetical';

/**
 * Props for MultiMarketAccordion
 */
export interface MultiMarketAccordionProps {
  /** List of markets to display */
  markets: AccordionMarket[];
  /** Number of markets to show initially (default: 5) */
  initialDisplayCount?: number;
  /** Whether to show the search input (default: true for 5+ markets) */
  showSearch?: boolean;
  /** Whether to show the sort dropdown (default: true for 3+ markets) */
  showSort?: boolean;
  /** Default sort option (default: 'probability') */
  defaultSort?: MarketSortOption;
  /** Expansion mode: 'single' allows one open, 'multiple' allows many */
  mode?: AccordionMode;
  /** Default expanded market ID(s) */
  defaultExpanded?: string | string[];
  /** Callback when expansion changes */
  onExpandChange?: (expandedIds: string[]) => void;
  /** Callback when a buy button is clicked */
  onTradeClick?: (selection: TradeSelection) => void;
  /** Whether to sync expanded state with URL hash */
  persistToUrl?: boolean;
  /** Real-time price update configuration */
  realtimePrices?: RealtimePriceConfig;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Sort label display names
 */
const SORT_LABELS: Record<MarketSortOption, string> = {
  probability: 'Probability',
  volume: 'Volume',
  alphabetical: 'A-Z',
};

/**
 * Get the primary probability for sorting (highest outcome price)
 */
function getPrimaryProbability(market: AccordionMarket): number {
  if (market.outcomes.length === 0) return 0;
  return Math.max(...market.outcomes.map((o) => o.currentPrice));
}

/**
 * Sort markets based on the selected option
 */
function sortMarkets(
  markets: AccordionMarket[],
  sortOption: MarketSortOption
): AccordionMarket[] {
  const sorted = [...markets];

  switch (sortOption) {
    case 'probability':
      // Sort by highest outcome probability, descending
      return sorted.sort((a, b) => getPrimaryProbability(b) - getPrimaryProbability(a));

    case 'volume':
      // Sort by total volume, descending
      return sorted.sort((a, b) => (b.totalVolume || 0) - (a.totalVolume || 0));

    case 'alphabetical':
      // Sort by question, ascending
      return sorted.sort((a, b) => a.question.localeCompare(b.question));

    default:
      return sorted;
  }
}

/**
 * Filter markets based on search query
 */
function filterMarkets(
  markets: AccordionMarket[],
  searchQuery: string
): AccordionMarket[] {
  if (!searchQuery.trim()) return markets;

  const query = searchQuery.toLowerCase().trim();
  return markets.filter((market) => {
    // Search in market question
    if (market.question.toLowerCase().includes(query)) return true;

    // Search in outcome names
    if (market.outcomes.some((o) => o.outcomeName.toLowerCase().includes(query))) {
      return true;
    }

    return false;
  });
}

/**
 * MultiMarketAccordion - Wrapper for handling events with many markets
 *
 * PRD: multi_market_layout
 *
 * Features:
 * - Support events with 10+ markets
 * - 'Show all X markets' expandable section for long lists
 * - Display top N markets by volume/probability, collapse rest
 * - Search/filter input for finding specific markets
 * - Sort markets by: probability (default), volume, alphabetical
 * - 'X more markets' indicator when collapsed
 *
 * @example
 * ```tsx
 * <MultiMarketAccordion
 *   markets={markets}
 *   initialDisplayCount={5}
 *   defaultSort="probability"
 * />
 * ```
 */
export function MultiMarketAccordion({
  markets,
  initialDisplayCount = 5,
  showSearch,
  showSort,
  defaultSort = 'probability',
  mode = 'single',
  defaultExpanded,
  onExpandChange,
  onTradeClick,
  persistToUrl = true,
  realtimePrices,
  className,
}: MultiMarketAccordionProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOption, setSortOption] = useState<MarketSortOption>(defaultSort);
  const [showAll, setShowAll] = useState(false);
  const [isSortOpen, setIsSortOpen] = useState(false);

  // Determine whether to show search and sort based on market count
  const shouldShowSearch = showSearch ?? markets.length >= 5;
  const shouldShowSort = showSort ?? markets.length >= 3;

  // Filter and sort markets
  const processedMarkets = useMemo(() => {
    const filtered = filterMarkets(markets, searchQuery);
    return sortMarkets(filtered, sortOption);
  }, [markets, searchQuery, sortOption]);

  // Determine visible markets
  const visibleMarkets = useMemo(() => {
    // If searching, show all matching results
    if (searchQuery.trim()) return processedMarkets;

    // If show all is enabled, show all
    if (showAll) return processedMarkets;

    // Otherwise, limit to initial display count
    return processedMarkets.slice(0, initialDisplayCount);
  }, [processedMarkets, searchQuery, showAll, initialDisplayCount]);

  // Calculate hidden count
  const hiddenCount = processedMarkets.length - visibleMarkets.length;
  const hasMore = hiddenCount > 0;

  // Handle search input change
  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    // Reset show all when searching
    setShowAll(false);
  }, []);

  // Clear search
  const clearSearch = useCallback(() => {
    setSearchQuery('');
  }, []);

  // Toggle show all
  const toggleShowAll = useCallback(() => {
    setShowAll((prev) => !prev);
  }, []);

  // Handle sort selection
  const handleSortChange = useCallback((option: MarketSortOption) => {
    setSortOption(option);
    setIsSortOpen(false);
  }, []);

  // Close sort dropdown on click outside
  useEffect(() => {
    if (!isSortOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-sort-dropdown]')) {
        setIsSortOpen(false);
      }
    };

    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [isSortOpen]);

  // Empty state when no markets
  if (markets.length === 0) {
    return (
      <div className={cn('rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500', className)}>
        No markets found for this event.
      </div>
    );
  }

  // No search results
  if (processedMarkets.length === 0 && searchQuery.trim()) {
    return (
      <div className={cn('space-y-3', className)}>
        {/* Search and Sort Controls */}
        <MultiMarketControls
          searchQuery={searchQuery}
          onSearchChange={handleSearchChange}
          onClearSearch={clearSearch}
          showSearch={shouldShowSearch}
          sortOption={sortOption}
          onSortChange={handleSortChange}
          showSort={shouldShowSort}
          isSortOpen={isSortOpen}
          onSortToggle={() => setIsSortOpen(!isSortOpen)}
        />

        {/* No results message */}
        <div className="rounded-lg border border-gray-200 bg-white p-8 text-center">
          <Search className="h-8 w-8 mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">
            No markets found matching &ldquo;{searchQuery}&rdquo;
          </p>
          <button
            onClick={clearSearch}
            className="mt-3 text-sm text-indigo-600 hover:text-indigo-700 font-medium"
          >
            Clear search
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('space-y-3', className)}>
      {/* Search and Sort Controls */}
      {(shouldShowSearch || shouldShowSort) && (
        <MultiMarketControls
          searchQuery={searchQuery}
          onSearchChange={handleSearchChange}
          onClearSearch={clearSearch}
          showSearch={shouldShowSearch}
          sortOption={sortOption}
          onSortChange={handleSortChange}
          showSort={shouldShowSort}
          isSortOpen={isSortOpen}
          onSortToggle={() => setIsSortOpen(!isSortOpen)}
          totalCount={processedMarkets.length}
          showingCount={visibleMarkets.length}
        />
      )}

      {/* Market Accordion */}
      <MarketAccordion
        markets={visibleMarkets}
        mode={mode}
        defaultExpanded={defaultExpanded}
        onExpandChange={onExpandChange}
        onTradeClick={onTradeClick}
        persistToUrl={persistToUrl}
        realtimePrices={realtimePrices}
      />

      {/* Show More/Less Button */}
      {hasMore && !searchQuery.trim() && (
        <ShowMoreButton
          hiddenCount={hiddenCount}
          showAll={showAll}
          onToggle={toggleShowAll}
        />
      )}

      {/* Show Less Button when expanded */}
      {showAll && processedMarkets.length > initialDisplayCount && !searchQuery.trim() && (
        <ShowLessButton onToggle={toggleShowAll} />
      )}
    </div>
  );
}

/**
 * Controls for search and sort
 */
interface MultiMarketControlsProps {
  searchQuery: string;
  onSearchChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onClearSearch: () => void;
  showSearch: boolean;
  sortOption: MarketSortOption;
  onSortChange: (option: MarketSortOption) => void;
  showSort: boolean;
  isSortOpen: boolean;
  onSortToggle: () => void;
  totalCount?: number;
  showingCount?: number;
}

const MultiMarketControls = memo(function MultiMarketControls({
  searchQuery,
  onSearchChange,
  onClearSearch,
  showSearch,
  sortOption,
  onSortChange,
  showSort,
  isSortOpen,
  onSortToggle,
  totalCount,
  showingCount,
}: MultiMarketControlsProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
      {/* Search Input - full width on mobile */}
      {showSearch && (
        <div className="relative flex-1 sm:max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={onSearchChange}
            placeholder="Search markets..."
            className={cn(
              'w-full pl-9 pr-8 text-sm',
              // Mobile: Taller input for better touch target (min 44px)
              'py-2.5 sm:py-2',
              'border border-gray-200 rounded-lg',
              'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
              'placeholder:text-gray-400'
            )}
            data-testid="market-search-input"
          />
          {searchQuery && (
            <button
              onClick={onClearSearch}
              className={cn(
                'absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600',
                // Ensure touch target
                'p-2 -mr-1'
              )}
              aria-label="Clear search"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      )}

      {/* Sort Dropdown and Count - row on mobile, aligned right on desktop */}
      <div className="flex items-center justify-between sm:justify-end gap-2 sm:gap-3 sm:ml-auto">
        {/* Market Count */}
        {totalCount !== undefined && showingCount !== undefined && (
          <span className="text-xs text-gray-500" data-testid="market-count">
            {showingCount === totalCount
              ? `${totalCount} market${totalCount === 1 ? '' : 's'}`
              : `${showingCount} of ${totalCount}`}
          </span>
        )}

        {/* Sort Dropdown */}
        {showSort && (
          <div className="relative" data-sort-dropdown>
            <button
              onClick={onSortToggle}
              className={cn(
                'inline-flex items-center gap-1.5 text-sm font-medium',
                'border border-gray-200 rounded-lg bg-white',
                'hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500',
                'transition-colors',
                // Mobile: Ensure min touch target
                'px-2.5 py-2 min-h-[44px] sm:px-3 sm:py-2 sm:min-h-0 sm:gap-2'
              )}
              aria-expanded={isSortOpen}
              aria-haspopup="true"
              data-testid="market-sort-button"
            >
              <ArrowUpDown className="h-4 w-4 text-gray-400" />
              <span className="text-gray-700">{SORT_LABELS[sortOption]}</span>
              <ChevronDown
                className={cn(
                  'h-4 w-4 text-gray-400 transition-transform',
                  isSortOpen && 'rotate-180'
                )}
              />
            </button>

            {/* Dropdown Menu */}
            {isSortOpen && (
              <div
                className={cn(
                  'absolute right-0 mt-1 w-40 py-1',
                  'bg-white border border-gray-200 rounded-lg shadow-lg',
                  'z-10 animate-in fade-in slide-in-from-top-2 duration-150'
                )}
                role="menu"
              >
                {(Object.keys(SORT_LABELS) as MarketSortOption[]).map((option) => (
                  <button
                    key={option}
                    onClick={() => onSortChange(option)}
                    className={cn(
                      'w-full text-left px-4 text-sm',
                      // Mobile: Larger touch targets in dropdown
                      'py-3 sm:py-2',
                      'hover:bg-gray-50 transition-colors',
                      sortOption === option
                        ? 'text-indigo-600 font-medium bg-indigo-50'
                        : 'text-gray-700'
                    )}
                    role="menuitem"
                    data-testid={`sort-option-${option}`}
                  >
                    {SORT_LABELS[option]}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

/**
 * Show More Button
 */
interface ShowMoreButtonProps {
  hiddenCount: number;
  showAll: boolean;
  onToggle: () => void;
}

const ShowMoreButton = memo(function ShowMoreButton({
  hiddenCount,
  onToggle,
}: ShowMoreButtonProps) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        'w-full px-4',
        // Mobile: Larger touch target (min 44px)
        'py-3.5 sm:py-3',
        'text-sm font-medium text-indigo-600',
        'border border-dashed border-gray-300 rounded-lg',
        'hover:border-indigo-300 hover:bg-indigo-50/50',
        'active:bg-indigo-100',
        'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2',
        'transition-colors flex items-center justify-center gap-2'
      )}
      data-testid="show-more-button"
    >
      <ChevronDown className="h-4 w-4" />
      Show {hiddenCount} more market{hiddenCount === 1 ? '' : 's'}
    </button>
  );
});

/**
 * Show Less Button
 */
interface ShowLessButtonProps {
  onToggle: () => void;
}

const ShowLessButton = memo(function ShowLessButton({ onToggle }: ShowLessButtonProps) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        'w-full px-4',
        // Mobile: Larger touch target (min 44px)
        'py-3.5 sm:py-3',
        'text-sm font-medium text-gray-600',
        'border border-dashed border-gray-300 rounded-lg',
        'hover:border-gray-400 hover:bg-gray-50',
        'active:bg-gray-100',
        'focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2',
        'transition-colors flex items-center justify-center gap-2'
      )}
      data-testid="show-less-button"
    >
      <ChevronUp className="h-4 w-4" />
      Show fewer markets
    </button>
  );
});

export default MarketAccordion;
