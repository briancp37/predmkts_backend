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
import { useCallback, useEffect, useState, memo } from 'react';
import * as Accordion from '@radix-ui/react-accordion';
import * as Tabs from '@radix-ui/react-tabs';
import { ChevronDown, TrendingUp, TrendingDown, BookOpen, LineChart, FileText, AlertCircle, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  formatProbability,
  formatProbabilityAsCents,
  getProbabilityColor,
} from './probability-display';
import { OrderBook } from './order-book';
import { PriceChart } from './price-chart';
import { TimeRangeSelector, TIME_RANGE_TO_INTERVAL, DEFAULT_TIME_RANGE, type TimeRange } from './time-range-selector';
import { ResolutionRules } from './resolution-rules';

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
        {markets.map((market) => (
          <MarketAccordionItem
            key={market.id}
            market={market}
            onTradeClick={onTradeClick}
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
      {markets.map((market) => (
        <MarketAccordionItem
          key={market.id}
          market={market}
          onTradeClick={onTradeClick}
        />
      ))}
    </Accordion.Root>
  );
}

interface MarketAccordionItemProps {
  market: AccordionMarket;
  onTradeClick?: (selection: TradeSelection) => void;
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
}

const MarketAccordionHeader = memo(function MarketAccordionHeader({
  market,
  primaryOutcome,
  allOutcomes,
  onTradeClick,
}: MarketAccordionHeaderProps) {
  const colors = primaryOutcome ? getProbabilityColor(primaryOutcome.currentPrice) : null;

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
    <Accordion.Trigger className="group flex w-full items-center justify-between p-4 text-left hover:bg-gray-50/80 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500 transition-colors data-[state=open]:bg-gray-50/50">
      <div className="flex flex-1 items-center gap-3 min-w-0 pr-4">
        {/* Optional avatar/image for candidate markets */}
        {market.imageUrl && (
          <div className="flex-shrink-0">
            <img
              src={market.imageUrl}
              alt=""
              className="h-10 w-10 rounded-full object-cover ring-2 ring-gray-100"
            />
          </div>
        )}

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Market Question / Candidate Name */}
          <h3 className="font-semibold text-gray-900 truncate text-base">
            {market.question}
          </h3>

          {/* Secondary info row: volume, bid/ask, liquidity */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs text-gray-500">
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
      </div>

      {/* Right side: Buy buttons, Price display and indicators */}
      <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
        {/* Buy Yes/No buttons - only show for binary markets with Yes/No outcomes */}
        {yesOutcome && noOutcome && (
          <div className="hidden sm:flex items-center gap-1.5">
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

            {/* Large probability display with color coding */}
            {colors && (
              <div
                className={cn(
                  'flex items-baseline gap-1 px-3 py-1.5 rounded-lg',
                  colors.bg
                )}
              >
                <span className={cn('text-2xl font-bold tabular-nums', colors.text)}>
                  {formatProbability(primaryOutcome.currentPrice)}
                </span>
                <span className={cn('text-xs font-medium', colors.text, 'opacity-70')}>
                  {formatProbabilityAsCents(primaryOutcome.currentPrice)}
                </span>
              </div>
            )}
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
 */
interface BuyButtonProps {
  outcome: MarketOutcome;
  variant: 'yes' | 'no';
  disabled: boolean;
  onClick: (e: React.MouseEvent) => void;
}

const BuyButton = memo(function BuyButton({
  outcome,
  variant,
  disabled,
  onClick,
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
        'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold',
        'transition-all duration-150 whitespace-nowrap',
        'focus:outline-none focus:ring-2 focus:ring-offset-1',
        variant === 'yes'
          ? disabled
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-green-100 text-green-700 hover:bg-green-200 focus:ring-green-500 hover:shadow-sm'
          : disabled
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-red-100 text-red-700 hover:bg-red-200 focus:ring-red-500 hover:shadow-sm'
      )}
    >
      <span>{outcome.outcomeName}</span>
      <span className="tabular-nums">{priceInCents}¢</span>
    </button>
  );
});

/**
 * PriceChangeIndicator - Shows 24h price change with trend icon
 */
interface PriceChangeIndicatorProps {
  /** Change value (absolute, e.g., 0.05 for 5%) */
  change: number;
}

const PriceChangeIndicator = memo(function PriceChangeIndicator({
  change,
}: PriceChangeIndicatorProps) {
  const isPositive = change > 0;
  const absChange = Math.abs(change * 100);
  const Icon = isPositive ? TrendingUp : TrendingDown;

  return (
    <div
      className={cn(
        'flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-md',
        isPositive ? 'text-green-700 bg-green-50' : 'text-red-700 bg-red-50'
      )}
      title={`24h change: ${isPositive ? '+' : '-'}${absChange.toFixed(1)}%`}
    >
      <Icon className="h-3 w-3" />
      <span>{absChange.toFixed(1)}%</span>
    </div>
  );
});

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
        {/* Tab List */}
        <div className="border-b border-gray-200 bg-white rounded-t-lg">
          <Tabs.List
            className="flex overflow-x-auto scrollbar-hide"
            aria-label="Market details tabs"
          >
            {ACCORDION_TABS.map((tab) => (
              <Tabs.Trigger
                key={tab.value}
                value={tab.value}
                className={cn(
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap',
                  'border-b-2 transition-colors duration-200',
                  'hover:text-gray-900 hover:bg-gray-50',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2',
                  'data-[state=active]:border-indigo-600 data-[state=active]:text-indigo-600',
                  'data-[state=inactive]:border-transparent data-[state=inactive]:text-gray-500'
                )}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </div>

        {/* Tab Content */}
        <div className="p-4 bg-white rounded-b-lg">
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
 * OrderBookTabContent - Lazy-loaded Order Book tab wrapper
 */
interface OrderBookTabContentProps {
  tokenId: string | undefined;
}

const OrderBookTabContent = memo(function OrderBookTabContent({
  tokenId,
}: OrderBookTabContentProps) {
  if (!tokenId) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-gray-500">
        Select an outcome to view the order book
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
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
          {/* Buy buttons (hidden on mobile) */}
          <div className="hidden sm:flex items-center gap-1.5">
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

export default MarketAccordion;
