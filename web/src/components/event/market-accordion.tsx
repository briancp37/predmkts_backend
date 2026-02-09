/**
 * Market Accordion Component
 *
 * Sprint 07 - Expandable Market Accordion
 * PRD: market_accordion_container, market_accordion_header
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
 */

'use client';

import { useCallback, useEffect, useState, memo } from 'react';
import * as Accordion from '@radix-ui/react-accordion';
import { ChevronDown, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  formatProbability,
  formatProbabilityAsCents,
  getProbabilityColor,
} from './probability-display';

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
}

/**
 * Accordion expansion mode
 */
export type AccordionMode = 'single' | 'multiple';

export interface MarketAccordionProps {
  /** List of markets to display */
  markets: AccordionMarket[];
  /** Expansion mode: 'single' allows one open, 'multiple' allows many */
  mode?: AccordionMode;
  /** Default expanded market ID(s) */
  defaultExpanded?: string | string[];
  /** Callback when expansion changes */
  onExpandChange?: (expandedIds: string[]) => void;
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
        />
      ))}
    </Accordion.Root>
  );
}

interface MarketAccordionItemProps {
  market: AccordionMarket;
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
}

const MarketAccordionHeader = memo(function MarketAccordionHeader({
  market,
  primaryOutcome,
}: MarketAccordionHeaderProps) {
  const colors = primaryOutcome ? getProbabilityColor(primaryOutcome.currentPrice) : null;

  // Format bid/ask spread for display
  const bidAskSpread =
    primaryOutcome?.bestBid !== undefined && primaryOutcome?.bestAsk !== undefined
      ? `${Math.round(primaryOutcome.bestBid * 100)}¢ / ${Math.round(primaryOutcome.bestAsk * 100)}¢`
      : null;

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

      {/* Right side: Price display and indicators */}
      <div className="flex items-center gap-3 flex-shrink-0">
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
 * Individual accordion item for a market
 */
const MarketAccordionItem = memo(function MarketAccordionItem({ market }: MarketAccordionItemProps) {
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
        <MarketAccordionHeader market={market} primaryOutcome={primaryOutcome} />
      </Accordion.Header>

      <Accordion.Content className="overflow-hidden data-[state=open]:animate-accordion-down data-[state=closed]:animate-accordion-up">
        <div className="border-t border-gray-100 p-4 bg-gray-50/30">
          {/* Placeholder for tab content - will be implemented in market_accordion_content */}
          <div className="text-sm text-gray-500">
            <p className="text-gray-400 mb-3">Market details and trading options</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {market.outcomes.map((outcome) => {
                const outcomeColors = getProbabilityColor(outcome.currentPrice);
                return (
                  <div
                    key={outcome.id}
                    className="flex items-center justify-between p-2 rounded-md bg-white border border-gray-100"
                  >
                    <span className="font-medium text-gray-700">{outcome.outcomeName}</span>
                    <div className="flex items-center gap-2">
                      {outcome.priceChange24h !== undefined && outcome.priceChange24h !== 0 && (
                        <span
                          className={cn(
                            'text-xs',
                            outcome.priceChange24h > 0 ? 'text-green-600' : 'text-red-600'
                          )}
                        >
                          {outcome.priceChange24h > 0 ? '+' : ''}
                          {(outcome.priceChange24h * 100).toFixed(1)}%
                        </span>
                      )}
                      <span className={cn('text-sm font-semibold px-2 py-0.5 rounded', outcomeColors.bg, outcomeColors.text)}>
                        {formatProbability(outcome.currentPrice)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
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

export default MarketAccordion;
