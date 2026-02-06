/**
 * React Query hooks for market data fetching
 *
 * Calls FastAPI backend at /api/v1/markets
 *
 * Provides:
 * - useMarkets() - Fetch markets with filtering and pagination
 * - useMarket(id) - Fetch single market by id, polymarketId, or slug
 */

'use client';

import { useQuery } from '@tanstack/react-query';

const API_BASE = '/api/v1';

/**
 * Market outcome type (token)
 */
export interface MarketOutcome {
  id: string;
  tokenId: string;
  outcomeName: string;
  currentPrice: number;
  volume: number;
}

/**
 * Market type matching FastAPI MarketResponse schema
 */
export interface Market {
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
  outcomes: MarketOutcome[];
}

/**
 * Response type for /api/v1/markets endpoint (FastAPI MarketListResponse)
 */
export interface MarketsResponse {
  items: Market[];
  total: number;
  page: number;
  limit: number;
}

/**
 * Query parameters for useMarkets hook
 */
export interface UseMarketsParams {
  /** Search by question text (case-insensitive) */
  search?: string;
  /** Filter by category */
  category?: string;
  /** Filter by resolved status */
  resolved?: boolean;
  /** Number of results (default: 20, max: 100) */
  limit?: number;
  /** Pagination offset (default: 0) */
  offset?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch markets from the API
 */
async function fetchMarkets(params: Omit<UseMarketsParams, 'enabled'>): Promise<MarketsResponse> {
  const searchParams = new URLSearchParams();

  if (params.search) {
    searchParams.set('search', params.search);
  }
  if (params.category) {
    searchParams.set('category', params.category);
  }
  if (params.resolved !== undefined) {
    searchParams.set('resolved', String(params.resolved));
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.offset !== undefined) {
    searchParams.set('offset', String(params.offset));
  }

  const queryString = searchParams.toString();
  const url = `${API_BASE}/markets${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to fetch markets: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch markets with filtering and pagination
 *
 * @example
 * ```tsx
 * // Fetch all markets
 * const { data, isLoading, error } = useMarkets();
 *
 * // Fetch with filters
 * const { data } = useMarkets({
 *   search: 'election',
 *   category: 'politics',
 *   resolved: false,
 *   limit: 10,
 * });
 *
 * // Paginate
 * const { data } = useMarkets({ offset: 20 });
 * ```
 */
export function useMarkets(params: UseMarketsParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['markets', queryParams],
    queryFn: () => fetchMarkets(queryParams),
    enabled,
  });
}

/**
 * Fetch a single market from the FastAPI backend
 */
async function fetchMarket(id: string): Promise<Market> {
  const response = await fetch(`${API_BASE}/markets/${encodeURIComponent(id)}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to fetch market: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch a single market by id, polymarketId, or slug
 *
 * @example
 * ```tsx
 * // Fetch by internal id
 * const { data, isLoading, error } = useMarket('clx123...');
 *
 * // Fetch by slug
 * const { data } = useMarket('will-trump-win-2024');
 *
 * // Fetch by polymarketId
 * const { data } = useMarket('0x123...');
 *
 * // Disable query until ready
 * const { data } = useMarket(selectedId, { enabled: !!selectedId });
 * ```
 */
export function useMarket(id: string | undefined | null, options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: ['market', id],
    queryFn: () => fetchMarket(id!),
    enabled: enabled && !!id,
  });
}
