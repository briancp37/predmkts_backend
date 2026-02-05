/**
 * React Query hooks for Markets page data fetching
 *
 * PRD #5 - Create React Query hooks for Markets page data fetching
 *
 * Provides:
 * - useMarketsAdvanced(params) - Fetch markets with CLOB data and comprehensive filtering
 *
 * Features:
 * - All filter parameters (category, volume, liquidity, spread, time, tags)
 * - Debouncing built into the hook via queryKey changes
 * - Full pagination support
 */

'use client';

import { useQuery, keepPreviousData } from '@tanstack/react-query';

/**
 * Market outcome type for advanced API
 */
export interface AdvancedMarketOutcome {
  id: string;
  tokenId: string;
  outcomeName: string;
  currentPrice: number;
  volume: number;
}

/**
 * Advanced market data with CLOB bid/ask info
 */
export interface AdvancedMarket {
  id: string;
  polymarketId: string;
  conditionId: string | null;
  slug: string | null;
  question: string;
  description: string | null;
  category: string | null;
  endDate: string | null;
  resolved: boolean;
  totalVolume: number;
  liquidity: number;
  createdAt: string;
  imageUrl: string | null;
  outcomes: AdvancedMarketOutcome[];
  // CLOB data
  bid: number | null;
  ask: number | null;
  spread: number | null;
  spreadPercent: number | null;
  spreadCents: number | null;
  // 24h stats
  volume24h: number;
  priceChange24h: number;
}

/**
 * Pagination metadata from API response
 */
export interface PaginationMeta {
  limit: number;
  offset: number;
  page: number;
  totalPages: number;
}

/**
 * Response type for /api/markets/advanced endpoint
 */
export interface AdvancedMarketsResponse {
  markets: AdvancedMarket[];
  total: number;
  pagination: PaginationMeta;
}

/**
 * Sort options for markets
 */
export type MarketSortBy = 'volume' | 'liquidity' | 'spread';
export type SortOrder = 'asc' | 'desc';

/**
 * Time filter options
 */
export type TimeFilter = 'all' | '1d' | '7d' | '30d';

/**
 * Query parameters for useMarketsAdvanced hook
 */
export interface UseMarketsAdvancedParams {
  /** Filter by category */
  category?: string;
  /** Sort field (default: volume) */
  sortBy?: MarketSortBy;
  /** Sort direction (default: desc) */
  sortOrder?: SortOrder;
  /** Minimum total volume */
  minVolume?: number;
  /** Maximum total volume */
  maxVolume?: number;
  /** Minimum liquidity */
  minLiquidity?: number;
  /** Maximum liquidity */
  maxLiquidity?: number;
  /** Minimum spread percentage */
  minSpread?: number;
  /** Maximum spread percentage */
  maxSpread?: number;
  /** Minimum spread in cents */
  minSpreadCents?: number;
  /** Maximum spread in cents */
  maxSpreadCents?: number;
  /** Time remaining filter */
  timeRemaining?: TimeFilter;
  /** Created date filter */
  createdDate?: TimeFilter;
  /** Minimum 24h price change percentage */
  minChange?: number;
  /** Maximum 24h price change percentage */
  maxChange?: number;
  /** Comma-separated list of tags */
  tags?: string;
  /** Results per page (default: 25, max: 1000) */
  limit?: number;
  /** Pagination offset */
  offset?: number;
  /** Page number (alternative to offset) */
  page?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch markets from the advanced API
 */
async function fetchMarketsAdvanced(
  params: Omit<UseMarketsAdvancedParams, 'enabled'>
): Promise<AdvancedMarketsResponse> {
  const searchParams = new URLSearchParams();

  // Category filter
  if (params.category) {
    searchParams.set('category', params.category);
  }

  // Sort options
  if (params.sortBy) {
    searchParams.set('sortBy', params.sortBy);
  }
  if (params.sortOrder) {
    searchParams.set('sortOrder', params.sortOrder);
  }

  // Volume range filters
  if (params.minVolume !== undefined) {
    searchParams.set('minVolume', String(params.minVolume));
  }
  if (params.maxVolume !== undefined) {
    searchParams.set('maxVolume', String(params.maxVolume));
  }

  // Liquidity range filters
  if (params.minLiquidity !== undefined) {
    searchParams.set('minLiquidity', String(params.minLiquidity));
  }
  if (params.maxLiquidity !== undefined) {
    searchParams.set('maxLiquidity', String(params.maxLiquidity));
  }

  // Spread range filters
  if (params.minSpread !== undefined) {
    searchParams.set('minSpread', String(params.minSpread));
  }
  if (params.maxSpread !== undefined) {
    searchParams.set('maxSpread', String(params.maxSpread));
  }
  if (params.minSpreadCents !== undefined) {
    searchParams.set('minSpreadCents', String(params.minSpreadCents));
  }
  if (params.maxSpreadCents !== undefined) {
    searchParams.set('maxSpreadCents', String(params.maxSpreadCents));
  }

  // Time filters
  if (params.timeRemaining) {
    searchParams.set('timeRemaining', params.timeRemaining);
  }
  if (params.createdDate) {
    searchParams.set('createdDate', params.createdDate);
  }

  // Price change filters
  if (params.minChange !== undefined) {
    searchParams.set('minChange', String(params.minChange));
  }
  if (params.maxChange !== undefined) {
    searchParams.set('maxChange', String(params.maxChange));
  }

  // Tags filter
  if (params.tags) {
    searchParams.set('tags', params.tags);
  }

  // Pagination
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.offset !== undefined) {
    searchParams.set('offset', String(params.offset));
  }
  if (params.page !== undefined) {
    searchParams.set('page', String(params.page));
  }

  const queryString = searchParams.toString();
  const url = `/api/markets/advanced${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to fetch markets: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch markets with CLOB bid/ask data and comprehensive filtering
 *
 * @example
 * ```tsx
 * // Fetch markets with default sorting (by volume)
 * const { data, isLoading, error } = useMarketsAdvanced();
 *
 * // Fetch with filters
 * const { data } = useMarketsAdvanced({
 *   category: 'politics',
 *   sortBy: 'liquidity',
 *   minVolume: 10000,
 *   timeRemaining: '7d',
 * });
 *
 * // Paginate
 * const { data } = useMarketsAdvanced({ page: 2, limit: 50 });
 *
 * // Access market data with CLOB info
 * data?.markets.forEach(market => {
 *   console.log(market.question, market.bid, market.ask, market.spreadPercent);
 * });
 * ```
 */
export function useMarketsAdvanced(params: UseMarketsAdvancedParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['marketsAdvanced', queryParams],
    queryFn: () => fetchMarketsAdvanced(queryParams),
    enabled,
    // Keep previous data while fetching new data (smoother pagination)
    placeholderData: keepPreviousData,
    // Stale time of 30 seconds for CLOB data (reasonably fresh)
    staleTime: 30 * 1000,
  });
}
