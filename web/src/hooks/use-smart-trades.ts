/**
 * React Query hooks for smart trades and whale trades (ClickHouse/FastAPI)
 *
 * Sprint 03 - Trader Endpoints: Frontend Hooks Update
 *
 * Provides:
 * - useSmartTrades(params) - Fetch recent trades from smart traders
 * - useWhaleTrades(params) - Fetch recent large trades
 * - useSmartScores(params) - Fetch smart trader scores and rankings
 *
 * All hooks call the FastAPI backend via /api/v1/trades and /api/v1/traders endpoints.
 */

'use client';

import { useQuery, keepPreviousData } from '@tanstack/react-query';

// =============================================================================
// Types matching FastAPI schemas
// =============================================================================

/**
 * Base trade record
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
 * Trade with trader's smart score
 */
export interface SmartTrade extends Trade {
  smartScore: number;
}

/**
 * Trade with trader's total portfolio value
 */
export interface WhaleTrade extends Trade {
  totalWalletValue: number;
}

/**
 * Smart score components breakdown
 */
export interface SmartScoreComponents {
  accuracy: number;
  consistency: number;
  sizing: number;
  timing: number;
}

/**
 * Smart score for a trader
 */
export interface SmartScore {
  address: string;
  smartScore: number;
  components: SmartScoreComponents;
}

/**
 * Smart scores list response
 */
export interface SmartScoreListResponse {
  items: SmartScore[];
  timeWindow: string;
  generatedAt: string;
}

// =============================================================================
// useSmartTrades - Recent trades from smart traders
// =============================================================================

/**
 * Query parameters for useSmartTrades hook
 */
export interface UseSmartTradesParams {
  /** Minimum smart score threshold (0-100, default: 70) */
  minScore?: number;
  /** Minimum USD value filter */
  minAmount?: number;
  /** Maximum number of trades (default: 50, max: 200) */
  limit?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch smart trades from the FastAPI backend
 */
async function fetchSmartTrades(
  params: Omit<UseSmartTradesParams, 'enabled'>
): Promise<SmartTrade[]> {
  const searchParams = new URLSearchParams();

  if (params.minScore !== undefined) {
    searchParams.set('minScore', String(params.minScore));
  }
  if (params.minAmount !== undefined) {
    searchParams.set('minAmount', String(params.minAmount));
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }

  const queryString = searchParams.toString();
  const url = `/api/v1/trades/smart${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch smart trades: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch recent trades from smart traders
 *
 * @example
 * ```tsx
 * // Fetch trades from smart traders (default: minScore >= 70)
 * const { data, isLoading, error } = useSmartTrades();
 *
 * // With custom filters
 * const { data } = useSmartTrades({
 *   minScore: 80,
 *   minAmount: 1000,
 *   limit: 100,
 * });
 *
 * // Access smart trades
 * data?.forEach(trade => {
 *   console.log(`${trade.traderAddress} (score: ${trade.smartScore}): ${trade.side} ${trade.usdValue}`);
 * });
 * ```
 */
export function useSmartTrades(params: UseSmartTradesParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['smartTrades', queryParams],
    queryFn: () => fetchSmartTrades(queryParams),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 15 * 1000, // 15 seconds - real-time trade data
  });
}

// =============================================================================
// useWhaleTrades - Recent large trades
// =============================================================================

/**
 * Query parameters for useWhaleTrades hook
 */
export interface UseWhaleTradesParams {
  /** Minimum USD value threshold (default: 10000) */
  minAmount?: number;
  /** Maximum number of trades (default: 50, max: 200) */
  limit?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch whale trades from the FastAPI backend
 */
async function fetchWhaleTrades(
  params: Omit<UseWhaleTradesParams, 'enabled'>
): Promise<WhaleTrade[]> {
  const searchParams = new URLSearchParams();

  if (params.minAmount !== undefined) {
    searchParams.set('minAmount', String(params.minAmount));
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }

  const queryString = searchParams.toString();
  const url = `/api/v1/trades/whales${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch whale trades: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch recent large trades (whale trades)
 *
 * @example
 * ```tsx
 * // Fetch large trades (default: >= $10,000)
 * const { data, isLoading, error } = useWhaleTrades();
 *
 * // With custom minimum amount
 * const { data } = useWhaleTrades({ minAmount: 50000, limit: 25 });
 *
 * // Access whale trades
 * data?.forEach(trade => {
 *   console.log(`$${trade.usdValue} by wallet worth $${trade.totalWalletValue}`);
 * });
 * ```
 */
export function useWhaleTrades(params: UseWhaleTradesParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['whaleTrades', queryParams],
    queryFn: () => fetchWhaleTrades(queryParams),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 15 * 1000, // 15 seconds - real-time trade data
  });
}

// =============================================================================
// useSmartScores - Smart trader scores and rankings
// =============================================================================

/**
 * Time window options for smart score calculation
 */
export type SmartScoreTimeWindow = '7d' | '30d' | '90d' | 'all';

/**
 * Query parameters for useSmartScores hook
 */
export interface UseSmartScoresParams {
  /** Minimum smart score to include (0-100, default: 0) */
  minScore?: number;
  /** Maximum number of traders (default: 100, max: 500) */
  limit?: number;
  /** Time window for calculation (default: 30d) */
  timeWindow?: SmartScoreTimeWindow;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch smart scores from the FastAPI backend
 */
async function fetchSmartScores(
  params: Omit<UseSmartScoresParams, 'enabled'>
): Promise<SmartScoreListResponse> {
  const searchParams = new URLSearchParams();

  if (params.minScore !== undefined) {
    searchParams.set('minScore', String(params.minScore));
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.timeWindow) {
    searchParams.set('timeWindow', params.timeWindow);
  }

  const queryString = searchParams.toString();
  const url = `/api/v1/traders/smart-scores${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch smart scores: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch smart trader scores and rankings
 *
 * @example
 * ```tsx
 * // Fetch smart scores for last 30 days (default)
 * const { data, isLoading, error } = useSmartScores();
 *
 * // With custom parameters
 * const { data } = useSmartScores({
 *   minScore: 50,
 *   limit: 200,
 *   timeWindow: '90d',
 * });
 *
 * // Access smart scores with component breakdown
 * data?.items.forEach(score => {
 *   console.log(`${score.address}: ${score.smartScore}`);
 *   console.log(`  Accuracy: ${score.components.accuracy}`);
 *   console.log(`  Consistency: ${score.components.consistency}`);
 * });
 * ```
 */
export function useSmartScores(params: UseSmartScoresParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['smartScores', queryParams],
    queryFn: () => fetchSmartScores(queryParams),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60 * 1000, // 5 minutes - scores don't change frequently
  });
}
