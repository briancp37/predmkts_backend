/**
 * React Query hooks for Polymarket proxy endpoints
 *
 * Calls FastAPI backend at /api/v1/proxy/*
 *
 * Provides:
 * - useTimeseries() - Get price history for a token
 * - useOrderbook() - Get L2 order book with refetch interval
 * - useTopHolders() - Get top token holders for a market
 * - useMarketTrades() - Get recent trades for a market
 * - useMarketPrice() - Get real-time market info/prices
 * - useMarketTokens() - Get token ID mappings for a market
 *
 * Cache TTLs are configured to match backend cache:
 * - Orderbook: 5s (staleTime)
 * - Trades: 30s
 * - Market price: 10s
 * - Top holders: 5min
 * - Timeseries: varies by interval
 */

'use client';

import { useQuery } from '@tanstack/react-query';

const API_BASE = '/api/v1/proxy';

// ============================================================================
// Types
// ============================================================================

/**
 * Single price point in timeseries data
 */
export interface PricePoint {
  timestamp: number;
  price: number;
}

/**
 * Price history timeseries response
 */
export interface PriceHistoryResponse {
  tokenId: string;
  interval: string | null;
  fidelity: number | null;
  startTs: number | null;
  endTs: number | null;
  history: PricePoint[];
  cacheStatus: string;
}

/**
 * Valid interval options for timeseries queries
 */
export type TimeseriesInterval = '1m' | '5m' | '15m' | '1h' | '6h' | '1d' | '1w' | 'max';

/**
 * Single price level in the order book
 */
export interface OrderLevel {
  price: string;
  size: string;
}

/**
 * Order book (L2) response for a token
 */
export interface OrderBookResponse {
  tokenId: string;
  market: string;
  timestamp: string;
  bids: OrderLevel[];
  asks: OrderLevel[];
  spread: string | null;
  midPrice: string | null;
  bestBid: string | null;
  bestAsk: string | null;
  tickSize: string;
  minOrderSize: string;
  cacheStatus: string;
}

/**
 * Single trade from the activity feed
 */
export interface Trade {
  id: string;
  price: string;
  size: string;
  side: 'BUY' | 'SELL';
  timestamp: number;
  makerAddress: string | null;
  outcome: string | null;
  outcomeIndex: number | null;
}

/**
 * Response for recent trades query
 */
export interface RecentTradesResponse {
  tokenId: string;
  trades: Trade[];
  count: number;
  hasMore: boolean;
  cacheStatus: string;
}

/**
 * Valid trade side filter values
 */
export type TradeSide = 'BUY' | 'SELL';

/**
 * Price information for a single token/outcome
 */
export interface TokenPrice {
  tokenId: string;
  outcome: string;
  price: number;
  winner: boolean | null;
}

/**
 * Real-time market information
 */
export interface MarketInfoResponse {
  conditionId: string;
  question: string | null;
  tokens: TokenPrice[];
  active: boolean;
  closed: boolean;
  acceptingOrders: boolean;
  volume24h: number | null;
  liquidity: number | null;
  minimumOrderSize: number;
  minimumTickSize: number;
  dataSource: 'clob' | 'fallback';
  cacheStatus: string;
}

/**
 * Single holder in the top holders list
 */
export interface TopHolder {
  walletAddress: string;
  amount: string;
  pseudonym: string | null;
  name: string | null;
  profileImage: string | null;
  outcomeIndex: number | null;
}

/**
 * Response for top holders query
 */
export interface TopHoldersResponse {
  conditionId: string;
  tokenId: string | null;
  holders: TopHolder[];
  count: number;
  cacheStatus: string;
}

/**
 * Token information for a market outcome
 */
export interface TokenInfo {
  outcomeId: string;
  tokenId: string;
  side: string;
  outcomeLabel: string;
}

/**
 * Token ID mappings for a market
 */
export interface MarketTokensResponse {
  marketId: string;
  tokens: TokenInfo[];
  yesTokenId: string | null;
  noTokenId: string | null;
}

// ============================================================================
// Response Transformers (snake_case to camelCase)
// ============================================================================

function transformPriceHistoryResponse(data: Record<string, unknown>): PriceHistoryResponse {
  return {
    tokenId: data.token_id as string,
    interval: data.interval as string | null,
    fidelity: data.fidelity as number | null,
    startTs: data.start_ts as number | null,
    endTs: data.end_ts as number | null,
    history: (data.history as Array<{ t: number; p: number } | { timestamp: number; price: number }>).map((p) => ({
      timestamp: 't' in p ? p.t : p.timestamp,
      price: 'p' in p ? p.p : p.price,
    })),
    cacheStatus: data.cache_status as string,
  };
}

function transformOrderBookResponse(data: Record<string, unknown>): OrderBookResponse {
  return {
    tokenId: data.token_id as string,
    market: data.market as string,
    timestamp: data.timestamp as string,
    bids: data.bids as OrderLevel[],
    asks: data.asks as OrderLevel[],
    spread: data.spread as string | null,
    midPrice: data.mid_price as string | null,
    bestBid: data.best_bid as string | null,
    bestAsk: data.best_ask as string | null,
    tickSize: data.tick_size as string,
    minOrderSize: data.min_order_size as string,
    cacheStatus: data.cache_status as string,
  };
}

function transformTrade(t: Record<string, unknown>): Trade {
  return {
    id: t.id as string,
    price: t.price as string,
    size: t.size as string,
    side: t.side as 'BUY' | 'SELL',
    timestamp: t.timestamp as number,
    makerAddress: t.maker_address as string | null,
    outcome: t.outcome as string | null,
    outcomeIndex: t.outcome_index as number | null,
  };
}

function transformRecentTradesResponse(data: Record<string, unknown>): RecentTradesResponse {
  return {
    tokenId: data.token_id as string,
    trades: (data.trades as Array<Record<string, unknown>>).map(transformTrade),
    count: data.count as number,
    hasMore: data.has_more as boolean,
    cacheStatus: data.cache_status as string,
  };
}

function transformTokenPrice(t: Record<string, unknown>): TokenPrice {
  return {
    tokenId: t.token_id as string,
    outcome: t.outcome as string,
    price: t.price as number,
    winner: t.winner as boolean | null,
  };
}

function transformMarketInfoResponse(data: Record<string, unknown>): MarketInfoResponse {
  return {
    conditionId: data.condition_id as string,
    question: data.question as string | null,
    tokens: (data.tokens as Array<Record<string, unknown>>).map(transformTokenPrice),
    active: data.active as boolean,
    closed: data.closed as boolean,
    acceptingOrders: data.accepting_orders as boolean,
    volume24h: data.volume_24h as number | null,
    liquidity: data.liquidity as number | null,
    minimumOrderSize: data.minimum_order_size as number,
    minimumTickSize: data.minimum_tick_size as number,
    dataSource: data.data_source as 'clob' | 'fallback',
    cacheStatus: data.cache_status as string,
  };
}

function transformTopHolder(h: Record<string, unknown>): TopHolder {
  return {
    walletAddress: h.wallet_address as string,
    amount: h.amount as string,
    pseudonym: h.pseudonym as string | null,
    name: h.name as string | null,
    profileImage: h.profile_image as string | null,
    outcomeIndex: h.outcome_index as number | null,
  };
}

function transformTopHoldersResponse(data: Record<string, unknown>): TopHoldersResponse {
  return {
    conditionId: data.condition_id as string,
    tokenId: data.token_id as string | null,
    holders: (data.holders as Array<Record<string, unknown>>).map(transformTopHolder),
    count: data.count as number,
    cacheStatus: data.cache_status as string,
  };
}

function transformTokenInfo(t: Record<string, unknown>): TokenInfo {
  return {
    outcomeId: t.outcome_id as string,
    tokenId: t.token_id as string,
    side: t.side as string,
    outcomeLabel: t.outcome_label as string,
  };
}

function transformMarketTokensResponse(data: Record<string, unknown>): MarketTokensResponse {
  return {
    marketId: data.market_id as string,
    tokens: (data.tokens as Array<Record<string, unknown>>).map(transformTokenInfo),
    yesTokenId: data.yes_token_id as string | null,
    noTokenId: data.no_token_id as string | null,
  };
}

// ============================================================================
// Fetch Functions
// ============================================================================

async function fetchTimeseries(
  tokenId: string,
  params: {
    interval?: TimeseriesInterval;
    fidelity?: number;
    startTs?: number;
    endTs?: number;
  }
): Promise<PriceHistoryResponse> {
  const searchParams = new URLSearchParams();

  if (params.interval) {
    searchParams.set('interval', params.interval);
  }
  if (params.fidelity !== undefined) {
    searchParams.set('fidelity', String(params.fidelity));
  }
  if (params.startTs !== undefined) {
    searchParams.set('startTs', String(params.startTs));
  }
  if (params.endTs !== undefined) {
    searchParams.set('endTs', String(params.endTs));
  }

  const queryString = searchParams.toString();
  const url = `${API_BASE}/markets/${encodeURIComponent(tokenId)}/timeseries${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch timeseries: ${response.status}`);
  }

  const data = await response.json();
  return transformPriceHistoryResponse(data);
}

async function fetchOrderbook(tokenId: string, depth?: number): Promise<OrderBookResponse> {
  const searchParams = new URLSearchParams();

  if (depth !== undefined) {
    searchParams.set('depth', String(depth));
  }

  const queryString = searchParams.toString();
  const url = `${API_BASE}/markets/${encodeURIComponent(tokenId)}/orderbook${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch orderbook: ${response.status}`);
  }

  const data = await response.json();
  return transformOrderBookResponse(data);
}

async function fetchTrades(
  conditionId: string,
  params: {
    limit?: number;
    side?: TradeSide;
    maker?: string;
  }
): Promise<RecentTradesResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.side) {
    searchParams.set('side', params.side);
  }
  if (params.maker) {
    searchParams.set('maker', params.maker);
  }

  const queryString = searchParams.toString();
  const url = `${API_BASE}/markets/${encodeURIComponent(conditionId)}/trades${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch trades: ${response.status}`);
  }

  const data = await response.json();
  return transformRecentTradesResponse(data);
}

async function fetchMarketInfo(conditionId: string): Promise<MarketInfoResponse> {
  const url = `${API_BASE}/markets/${encodeURIComponent(conditionId)}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch market info: ${response.status}`);
  }

  const data = await response.json();
  return transformMarketInfoResponse(data);
}

async function fetchTopHolders(
  conditionId: string,
  params: {
    limit?: number;
    minBalance?: number;
  }
): Promise<TopHoldersResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.minBalance !== undefined) {
    searchParams.set('minBalance', String(params.minBalance));
  }

  const queryString = searchParams.toString();
  const url = `${API_BASE}/markets/${encodeURIComponent(conditionId)}/top-holders${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch top holders: ${response.status}`);
  }

  const data = await response.json();
  return transformTopHoldersResponse(data);
}

async function fetchMarketTokens(marketId: string): Promise<MarketTokensResponse> {
  const url = `${API_BASE}/markets/${encodeURIComponent(marketId)}/tokens`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch market tokens: ${response.status}`);
  }

  const data = await response.json();
  return transformMarketTokensResponse(data);
}

// ============================================================================
// Cache TTL Constants (matching backend cache TTLs)
// ============================================================================

/**
 * Stale time for timeseries by interval (in milliseconds)
 */
const TIMESERIES_STALE_TIME: Record<string, number> = {
  '1m': 30 * 1000,     // 30 seconds
  '5m': 60 * 1000,     // 1 minute
  '15m': 120 * 1000,   // 2 minutes
  '1h': 300 * 1000,    // 5 minutes
  '6h': 600 * 1000,    // 10 minutes
  '1d': 3600 * 1000,   // 1 hour
  '1w': 3600 * 1000,   // 1 hour
  'max': 3600 * 1000,  // 1 hour
  'default': 60 * 1000, // 1 minute for date range queries
};

const ORDERBOOK_STALE_TIME = 5 * 1000;     // 5 seconds
const TRADES_STALE_TIME = 30 * 1000;       // 30 seconds
const MARKET_INFO_STALE_TIME = 10 * 1000;  // 10 seconds
const TOP_HOLDERS_STALE_TIME = 300 * 1000; // 5 minutes
const MARKET_TOKENS_STALE_TIME = Infinity; // Token IDs don't change

// ============================================================================
// Hooks
// ============================================================================

/**
 * Query parameters for useTimeseries hook
 */
export interface UseTimeseriesParams {
  /** Time interval for data points. Mutually exclusive with startTs/endTs. */
  interval?: TimeseriesInterval;
  /** Resolution in minutes (1-60). Controls data granularity. */
  fidelity?: number;
  /** Start Unix timestamp (UTC). Use with endTs for custom date range. */
  startTs?: number;
  /** End Unix timestamp (UTC). Use with startTs for custom date range. */
  endTs?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Hook to fetch price history timeseries for a token
 *
 * @example
 * ```tsx
 * // Fetch 1-hour interval data
 * const { data, isLoading, error } = useTimeseries('token123', { interval: '1h' });
 *
 * // Fetch with custom date range
 * const { data } = useTimeseries('token123', {
 *   startTs: 1697788800,
 *   endTs: 1697875200,
 *   fidelity: 15,
 * });
 *
 * // Disable until ready
 * const { data } = useTimeseries(tokenId, { interval: '1d', enabled: !!tokenId });
 * ```
 */
export function useTimeseries(
  tokenId: string | undefined | null,
  params: UseTimeseriesParams = {}
) {
  const { enabled = true, ...queryParams } = params;

  // Determine stale time based on interval
  const staleTime = queryParams.interval
    ? TIMESERIES_STALE_TIME[queryParams.interval] || TIMESERIES_STALE_TIME.default
    : TIMESERIES_STALE_TIME.default;

  return useQuery({
    queryKey: ['proxy', 'timeseries', tokenId, queryParams],
    queryFn: () => fetchTimeseries(tokenId!, queryParams),
    enabled: enabled && !!tokenId,
    staleTime,
  });
}

/**
 * Query parameters for useOrderbook hook
 */
export interface UseOrderbookParams {
  /** Maximum number of bid/ask levels to return. Default returns all levels. */
  depth?: number;
  /** Refetch interval in milliseconds. Default: 5000 (5s) for real-time updates. */
  refetchInterval?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
  /** Number of retry attempts on failure. Default: 3 */
  retryCount?: number;
}

/**
 * Hook to fetch L2 order book for a token
 *
 * Automatically refetches every 5 seconds by default for real-time updates.
 * Implements exponential backoff retry on failure (1s, 2s, 4s).
 *
 * @example
 * ```tsx
 * // Fetch order book with default 5s refetch
 * const { data, isLoading, error, dataUpdatedAt } = useOrderbook('token123');
 *
 * // Limit depth and customize refetch interval
 * const { data } = useOrderbook('token123', { depth: 10, refetchInterval: 2000 });
 *
 * // Disable refetching
 * const { data } = useOrderbook('token123', { refetchInterval: false });
 *
 * // Check if data is stale (older than 10s)
 * const isStale = dataUpdatedAt && Date.now() - dataUpdatedAt > 10000;
 * ```
 */
export function useOrderbook(
  tokenId: string | undefined | null,
  params: UseOrderbookParams = {}
) {
  const { enabled = true, refetchInterval = 5000, depth, retryCount = 3 } = params;

  return useQuery({
    queryKey: ['proxy', 'orderbook', tokenId, depth],
    queryFn: () => fetchOrderbook(tokenId!, depth),
    enabled: enabled && !!tokenId,
    staleTime: ORDERBOOK_STALE_TIME,
    refetchInterval: refetchInterval || undefined,
    retry: retryCount,
    retryDelay: (attemptIndex) => Math.min(1000 * Math.pow(2, attemptIndex), 8000),
  });
}

/**
 * Query parameters for useMarketTrades hook
 */
export interface UseMarketTradesParams {
  /** Maximum number of trades to return (1-100). Default: 50 */
  limit?: number;
  /** Filter by trade side (BUY or SELL) */
  side?: TradeSide;
  /** Filter by maker wallet address */
  maker?: string;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
  /** Refetch interval in milliseconds. Set to false to disable. Default: no auto-refetch */
  refetchInterval?: number | false;
}

/**
 * Hook to fetch recent trades for a market
 *
 * @example
 * ```tsx
 * // Fetch recent trades
 * const { data, isLoading, error } = useMarketTrades('condition123');
 *
 * // Fetch with filters
 * const { data } = useMarketTrades('condition123', {
 *   limit: 20,
 *   side: 'BUY',
 * });
 * ```
 */
export function useMarketTrades(
  conditionId: string | undefined | null,
  params: UseMarketTradesParams = {}
) {
  const { enabled = true, refetchInterval, ...queryParams } = params;

  return useQuery({
    queryKey: ['proxy', 'trades', conditionId, queryParams],
    queryFn: () => fetchTrades(conditionId!, queryParams),
    enabled: enabled && !!conditionId,
    staleTime: TRADES_STALE_TIME,
    refetchInterval: refetchInterval === false ? undefined : refetchInterval,
  });
}

/**
 * Query parameters for useMarketPrice hook
 */
export interface UseMarketPriceParams {
  /** Refetch interval in milliseconds. Default: 10000 (10s) for semi-real-time updates. */
  refetchInterval?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Hook to fetch real-time market info/prices
 *
 * Automatically refetches every 10 seconds by default for semi-real-time updates.
 *
 * @example
 * ```tsx
 * // Fetch market price with default 10s refetch
 * const { data, isLoading, error } = useMarketPrice('condition123');
 *
 * // Customize refetch interval
 * const { data } = useMarketPrice('condition123', { refetchInterval: 5000 });
 *
 * // Access current prices
 * const yesPrice = data?.tokens.find(t => t.outcome === 'Yes')?.price;
 * ```
 */
export function useMarketPrice(
  conditionId: string | undefined | null,
  params: UseMarketPriceParams = {}
) {
  const { enabled = true, refetchInterval = 10000 } = params;

  return useQuery({
    queryKey: ['proxy', 'market-info', conditionId],
    queryFn: () => fetchMarketInfo(conditionId!),
    enabled: enabled && !!conditionId,
    staleTime: MARKET_INFO_STALE_TIME,
    refetchInterval: refetchInterval || undefined,
  });
}

/**
 * Query parameters for useTopHolders hook
 */
export interface UseTopHoldersParams {
  /** Maximum number of holders to return (1-20). Default: 20 */
  limit?: number;
  /** Minimum token balance filter. Default: 1 */
  minBalance?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Hook to fetch top token holders for a market
 *
 * @example
 * ```tsx
 * // Fetch top 20 holders
 * const { data, isLoading, error } = useTopHolders('condition123');
 *
 * // Fetch with filters
 * const { data } = useTopHolders('condition123', {
 *   limit: 10,
 *   minBalance: 100,
 * });
 * ```
 */
export function useTopHolders(
  conditionId: string | undefined | null,
  params: UseTopHoldersParams = {}
) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['proxy', 'top-holders', conditionId, queryParams],
    queryFn: () => fetchTopHolders(conditionId!, queryParams),
    enabled: enabled && !!conditionId,
    staleTime: TOP_HOLDERS_STALE_TIME,
  });
}

/**
 * Query parameters for useMarketTokens hook
 */
export interface UseMarketTokensParams {
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Hook to fetch token ID mappings for a market
 *
 * Token IDs are required for CLOB API calls (order book, price history, etc.).
 * Results are cached indefinitely since token IDs don't change.
 *
 * @example
 * ```tsx
 * // Get token IDs for a market
 * const { data, isLoading, error } = useMarketTokens('market123');
 *
 * // Use yes/no token IDs
 * const yesTokenId = data?.yesTokenId;
 * const noTokenId = data?.noTokenId;
 *
 * // Then use with orderbook or timeseries
 * const { data: orderbook } = useOrderbook(yesTokenId);
 * ```
 */
export function useMarketTokens(
  marketId: string | undefined | null,
  params: UseMarketTokensParams = {}
) {
  const { enabled = true } = params;

  return useQuery({
    queryKey: ['proxy', 'market-tokens', marketId],
    queryFn: () => fetchMarketTokens(marketId!),
    enabled: enabled && !!marketId,
    staleTime: MARKET_TOKENS_STALE_TIME,
  });
}
