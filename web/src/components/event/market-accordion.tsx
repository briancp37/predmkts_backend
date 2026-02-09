/**
 * Market Accordion Component
 *
 * Sprint 07 - Expandable Market Accordion
 * PRD: market_accordion_container
 *
 * Features:
 * - Expandable market rows using Radix Accordion
 * - Supports 'single' mode (only one market open) and 'multiple' mode
 * - Smooth height animation on expand/collapse
 * - Keyboard navigation (arrow keys, enter, space)
 * - URL hash persistence for deep linking to specific markets
 * - Accepts markets array with outcomes, tokenIds, and metadata
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import * as Accordion from '@radix-ui/react-accordion';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

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
 * Individual accordion item for a market
 */
function MarketAccordionItem({ market }: MarketAccordionItemProps) {
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
      className="rounded-lg border border-gray-200 bg-white overflow-hidden"
    >
      <Accordion.Header className="flex">
        <Accordion.Trigger className="group flex flex-1 items-center justify-between p-4 text-left hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500 transition-colors">
          <div className="flex-1 min-w-0 pr-4">
            {/* Market Question */}
            <h3 className="font-medium text-gray-900 truncate">
              {market.question}
            </h3>

            {/* Primary outcome probability and stats */}
            {primaryOutcome && (
              <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
                <span className="font-semibold text-gray-900">
                  {primaryOutcome.outcomeName}: {(primaryOutcome.currentPrice * 100).toFixed(1)}%
                </span>
                {market.volume24h !== undefined && market.volume24h > 0 && (
                  <span>24h Vol: ${formatVolume(market.volume24h)}</span>
                )}
              </div>
            )}
          </div>

          {/* Chevron indicator */}
          <ChevronDown
            className={cn(
              'h-5 w-5 text-gray-400 transition-transform duration-200 flex-shrink-0',
              'group-data-[state=open]:rotate-180'
            )}
            aria-hidden="true"
          />
        </Accordion.Trigger>
      </Accordion.Header>

      <Accordion.Content className="overflow-hidden data-[state=open]:animate-accordion-down data-[state=closed]:animate-accordion-up">
        <div className="border-t border-gray-100 p-4">
          {/* Placeholder for tab content - will be implemented in market_accordion_content */}
          <div className="text-sm text-gray-500">
            <p>Expanded content for: {market.question}</p>
            <p className="mt-2">Outcomes:</p>
            <ul className="mt-1 space-y-1">
              {market.outcomes.map((outcome) => (
                <li key={outcome.id} className="flex justify-between">
                  <span>{outcome.outcomeName}</span>
                  <span className="font-medium">
                    {(outcome.currentPrice * 100).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Accordion.Content>
    </Accordion.Item>
  );
}

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
