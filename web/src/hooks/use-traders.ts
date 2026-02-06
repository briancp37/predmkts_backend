/**
 * React Query hooks for trader data fetching (ClickHouse/FastAPI)
 *
 * Sprint 03 - Trader Endpoints: Frontend Hooks Update
 *
 * Provides:
 * - useTraders(params) - Fetch traders with search, sorting, and pagination
 * - useTrader(address) - Fetch single trader by wallet address
 * - useTraderTrades(address, params) - Fetch trader's trades with pagination
 *
 * All hooks call the FastAPI backend via /api/v1/traders endpoints.
 */

'use client';

import { useQuery, keepPreviousData } from '@tanstack/react-query';

// =============================================================================
// Types matching FastAPI schemas (src/prediction_data/api/traders/schemas.py)
// =============================================================================

/**
 * Current position held by a trader
 */
export interface TraderPosition {
  marketId: string;
  marketQuestion: string;
  outcomeId: string;
  outcomeName: string;
  quantity: number;
  avgCost: number;
  currentPrice: number;
  unrealizedPnl: number;
  realizedPnl: number;
}

/**
 * Trader summary for list responses
 */
export interface Trader {
  id: string;
  address: string;
  username: string | null;
  firstSeen: string;
  totalPnl: number;
  realizedPnl: number;
  totalTrades: number;
  winCount: number;
  lossCount: number;
  smartScore: number | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * Detailed trader response with positions and stats
 */
export interface TraderDetail extends Trader {
  positions: TraderPosition[];
  tradeCount: number;
  winRate: number;
}

/**
 * Paginated trader list response
 */
export interface TraderListResponse {
  items: Trader[];
  total: number;
  page: number;
  limit: number;
}

/**
 * Trade record for a trader
 */
export interface Trade {
  id: string;
  traderAddress: string;
  marketId: string;
  marketQuestion: string;
  outcomeId: string;
  outcomeName: string;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  usdValue: number;
  fees: number;
  realizedPnl: number | null;
  timestamp: string;
}

/**
 * Paginated trade list response
 */
export interface TradeListResponse {
  items: Trade[];
  total: number;
  page: number;
  limit: number;
}

// =============================================================================
// useTraders - List traders with search and sorting
// =============================================================================

/**
 * Sort options for trader list
 */
export type TraderSortBy = 'smartScore' | 'totalPnl' | 'totalTrades' | 'winRate';
export type SortOrder = 'asc' | 'desc';

/**
 * Query parameters for useTraders hook
 */
export interface UseTradersParams {
  /** Search by wallet address prefix (case-insensitive) */
  search?: string;
  /** Sort field (default: totalPnl) */
  sortBy?: TraderSortBy;
  /** Sort direction (default: desc) */
  sortOrder?: SortOrder;
  /** Number of results (default: 50, max: 500) */
  limit?: number;
  /** Pagination offset (default: 0) */
  offset?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch traders from the FastAPI backend
 */
async function fetchTraders(
  params: Omit<UseTradersParams, 'enabled'>
): Promise<TraderListResponse> {
  const searchParams = new URLSearchParams();

  if (params.search) {
    searchParams.set('search', params.search);
  }
  if (params.sortBy) {
    searchParams.set('sortBy', params.sortBy);
  }
  if (params.sortOrder) {
    searchParams.set('sortOrder', params.sortOrder);
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.offset !== undefined) {
    searchParams.set('offset', String(params.offset));
  }

  const queryString = searchParams.toString();
  const url = `/api/v1/traders${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch traders: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch traders with search, sorting, and pagination
 *
 * @example
 * ```tsx
 * // Fetch traders sorted by PnL
 * const { data, isLoading, error } = useTraders();
 *
 * // Search by address and sort by smart score
 * const { data } = useTraders({
 *   search: '0x123',
 *   sortBy: 'smartScore',
 *   sortOrder: 'desc',
 * });
 *
 * // Paginate
 * const { data } = useTraders({ limit: 25, offset: 50 });
 *
 * // Access trader data
 * data?.items.forEach(trader => {
 *   console.log(trader.address, trader.totalPnl, trader.smartScore);
 * });
 * ```
 */
export function useTraders(params: UseTradersParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['traders', queryParams],
    queryFn: () => fetchTraders(queryParams),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000, // 30 seconds
  });
}

// =============================================================================
// useTrader - Single trader detail
// =============================================================================

/**
 * Fetch a single trader from the FastAPI backend
 */
async function fetchTrader(address: string): Promise<TraderDetail> {
  const response = await fetch(`/api/v1/traders/${encodeURIComponent(address)}`);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Trader not found');
    }
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch trader: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch a single trader by wallet address
 *
 * @example
 * ```tsx
 * // Fetch trader by address
 * const { data, isLoading, error } = useTrader('0x1234...');
 *
 * // Access trader data with positions
 * if (data) {
 *   console.log(data.totalPnl, data.winRate);
 *   data.positions.forEach(pos => {
 *     console.log(pos.marketQuestion, pos.unrealizedPnl);
 *   });
 * }
 *
 * // Disable query until ready
 * const { data } = useTrader(address, { enabled: !!address });
 * ```
 */
export function useTrader(address: string | undefined | null, options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: ['trader', address?.toLowerCase()],
    queryFn: () => fetchTrader(address!),
    enabled: enabled && !!address,
    staleTime: 30 * 1000, // 30 seconds
  });
}

// =============================================================================
// useTraderTrades - Trader's trade history
// =============================================================================

/**
 * Query parameters for useTraderTrades hook
 */
export interface UseTraderTradesParams {
  /** Number of results (default: 100, max: 1000) */
  limit?: number;
  /** Pagination offset (default: 0) */
  offset?: number;
  /** Filter trades on or after this date (YYYY-MM-DD) */
  startDate?: string;
  /** Filter trades on or before this date (YYYY-MM-DD) */
  endDate?: string;
  /** Filter to a specific market */
  marketId?: string;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch trader trades from the FastAPI backend
 */
async function fetchTraderTrades(
  address: string,
  params: Omit<UseTraderTradesParams, 'enabled'>
): Promise<TradeListResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.offset !== undefined) {
    searchParams.set('offset', String(params.offset));
  }
  if (params.startDate) {
    searchParams.set('startDate', params.startDate);
  }
  if (params.endDate) {
    searchParams.set('endDate', params.endDate);
  }
  if (params.marketId) {
    searchParams.set('marketId', params.marketId);
  }

  const queryString = searchParams.toString();
  const url = `/api/v1/traders/${encodeURIComponent(address)}/trades${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Trader not found');
    }
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch trader trades: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch a trader's trades with pagination and filtering
 *
 * @example
 * ```tsx
 * // Fetch trader's recent trades
 * const { data, isLoading, error } = useTraderTrades('0x1234...');
 *
 * // With pagination and date filter
 * const { data } = useTraderTrades('0x1234...', {
 *   limit: 50,
 *   offset: 100,
 *   startDate: '2024-01-01',
 * });
 *
 * // Access trade data
 * if (data) {
 *   data.items.forEach(trade => {
 *     console.log(trade.side, trade.usdValue, trade.marketQuestion);
 *   });
 * }
 *
 * // Disable query until ready
 * const { data } = useTraderTrades(address, { enabled: !!address });
 * ```
 */
export function useTraderTrades(
  address: string | undefined | null,
  params: UseTraderTradesParams = {}
) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['traderTrades', address?.toLowerCase(), queryParams],
    queryFn: () => fetchTraderTrades(address!, queryParams),
    enabled: enabled && !!address,
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000, // 30 seconds
  });
}
