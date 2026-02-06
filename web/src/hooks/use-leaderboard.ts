/**
 * React Query hook for PnL leaderboard data fetching (ClickHouse/FastAPI)
 *
 * Sprint 03 - Trader Endpoints: Frontend Hooks Update
 *
 * Provides:
 * - useLeaderboard(params) - Fetch PnL leaderboard by time period
 *
 * Calls the FastAPI backend via /api/v1/traders/leaderboard endpoint.
 */

'use client';

import { useQuery, keepPreviousData } from '@tanstack/react-query';

// =============================================================================
// Types matching FastAPI schemas (src/prediction_data/api/traders/schemas.py)
// =============================================================================

/**
 * Leaderboard time period options
 */
export type LeaderboardPeriod = '1d' | '7d' | '30d' | 'all';

/**
 * Entry in the PnL leaderboard
 */
export interface LeaderboardEntry {
  rank: number;
  traderAddress: string;
  pnl: number;
  tradeCount: number;
  winRate: number;
}

/**
 * Leaderboard API response
 */
export interface LeaderboardResponse {
  period: string;
  entries: LeaderboardEntry[];
  generatedAt: string;
}

// =============================================================================
// useLeaderboard - PnL leaderboard by time period
// =============================================================================

/**
 * Query parameters for useLeaderboard hook
 */
export interface UseLeaderboardParams {
  /** Time period for aggregation (default: 7d) */
  period?: LeaderboardPeriod;
  /** Maximum number of entries (default: 100, max: 500) */
  limit?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch leaderboard from the FastAPI backend
 */
async function fetchLeaderboard(
  params: Omit<UseLeaderboardParams, 'enabled'>
): Promise<LeaderboardResponse> {
  const searchParams = new URLSearchParams();

  if (params.period) {
    searchParams.set('period', params.period);
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }

  const queryString = searchParams.toString();
  const url = `/api/v1/traders/leaderboard${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch leaderboard: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch PnL leaderboard by time period
 *
 * @example
 * ```tsx
 * // Fetch 7-day leaderboard (default)
 * const { data, isLoading, error } = useLeaderboard();
 *
 * // Fetch 30-day leaderboard
 * const { data } = useLeaderboard({ period: '30d', limit: 50 });
 *
 * // Access leaderboard entries
 * data?.entries.forEach(entry => {
 *   console.log(`#${entry.rank} ${entry.traderAddress}: $${entry.pnl.toFixed(2)}`);
 * });
 *
 * // Disable query until ready
 * const { data } = useLeaderboard({ enabled: false });
 * ```
 */
export function useLeaderboard(params: UseLeaderboardParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['leaderboard', queryParams],
    queryFn: () => fetchLeaderboard(queryParams),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000, // 1 minute - leaderboard updates less frequently
  });
}
