/**
 * React Query hooks for trader data fetching
 *
 * PRD #10 - Create React Query hooks for data fetching
 *
 * Provides:
 * - useTrader(address) - Fetch single trader by wallet address
 * - useTraderTrades(address, params) - Fetch trader's trades with pagination
 */

'use client';

import { useQuery } from '@tanstack/react-query';

/**
 * Position market data (subset of Market)
 */
export interface PositionMarket {
  id: string;
  polymarketId: string;
  slug: string | null;
  question: string;
  category: string | null;
  resolved: boolean;
  outcome: string | null;
}

/**
 * Position outcome data (subset of MarketOutcome)
 */
export interface PositionOutcome {
  id: string;
  tokenId: string;
  outcomeName: string;
  currentPrice: number;
}

/**
 * Trader position type
 */
export interface TraderPosition {
  id: string;
  traderId: string;
  marketId: string;
  outcomeId: string;
  quantity: number;
  avgPrice: number;
  investedUsd: number;
  currentValue: number;
  realizedPnl: number;
  unrealizedPnl: number;
  market: PositionMarket;
  outcome: PositionOutcome;
}

/**
 * Trader type matching API response
 */
export interface Trader {
  id: string;
  address: string;
  username: string | null;
  firstSeen: string;
  smartScore: number | null;
  totalPnl: number;
  realizedPnl: number;
  totalTrades: number;
  winCount: number;
  lossCount: number;
  createdAt: string;
  updatedAt: string;
  positions: TraderPosition[];
  tradeCount: number;
}

/**
 * Trade market data (subset of Market)
 */
export interface TradeMarket {
  id: string;
  polymarketId: string;
  slug: string | null;
  question: string;
  category: string | null;
  resolved: boolean;
}

/**
 * Trade outcome data (subset of MarketOutcome)
 */
export interface TradeOutcome {
  id: string;
  tokenId: string;
  outcomeName: string;
  currentPrice: number;
}

/**
 * Trade type matching API response
 */
export interface Trade {
  id: string;
  traderId: string;
  marketId: string;
  outcomeId: string;
  side: 'BUY' | 'SELL';
  price: number;
  amount: number;
  usdValue: number;
  feesPaid: number;
  txHash: string | null;
  timestamp: string;
  market: TradeMarket;
  outcome: TradeOutcome;
}

/**
 * Response type for /api/traders/[address]/trades endpoint
 */
export interface TraderTradesResponse {
  trades: Trade[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Query parameters for useTraderTrades hook
 */
export interface UseTraderTradesParams {
  /** Number of results (default: 20, max: 100) */
  limit?: number;
  /** Pagination offset (default: 0) */
  offset?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch a single trader from the API
 */
async function fetchTrader(address: string): Promise<Trader> {
  const response = await fetch(`/api/traders/${encodeURIComponent(address)}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to fetch trader: ${response.status}`);
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
 * // Access trader data
 * if (data) {
 *   console.log(data.smartScore);
 *   console.log(data.totalPnl);
 *   console.log(data.positions);
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
  });
}

/**
 * Fetch trader trades from the API
 */
async function fetchTraderTrades(
  address: string,
  params: Omit<UseTraderTradesParams, 'enabled'>
): Promise<TraderTradesResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.offset !== undefined) {
    searchParams.set('offset', String(params.offset));
  }

  const queryString = searchParams.toString();
  const url = `/api/traders/${encodeURIComponent(address)}/trades${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to fetch trader trades: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch a trader's trades with pagination
 *
 * @example
 * ```tsx
 * // Fetch trader's trades
 * const { data, isLoading, error } = useTraderTrades('0x1234...');
 *
 * // With pagination
 * const { data } = useTraderTrades('0x1234...', { limit: 50, offset: 100 });
 *
 * // Access trade data
 * if (data) {
 *   data.trades.forEach(trade => {
 *     console.log(trade.side, trade.usdValue, trade.market.question);
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
  });
}
