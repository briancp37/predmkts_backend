/**
 * React Query hooks for data fetching
 *
 * PRD #10 - Create React Query hooks for data fetching
 *
 * Re-exports all hooks for cleaner imports:
 * @example
 * ```tsx
 * import { useMarkets, useMarket, useTrader, useTraderTrades } from '@/hooks';
 * import { useMarketsAdvanced, useWatchlist, useTags } from '@/hooks';
 * import { useLeaderboard, useSmartTrades, useSmartScores } from '@/hooks';
 * ```
 */

// Market hooks - calls FastAPI /api/v1/markets
export {
  useMarkets,
  useMarket,
  type Market,
  type MarketOutcome,
  type MarketsResponse,
  type UseMarketsParams,
} from './use-markets';

// Advanced market hooks - calls FastAPI /api/v1/markets/advanced
export {
  useMarketsAdvanced,
  type AdvancedMarket,
  type AdvancedMarketOutcome,
  type AdvancedMarketsResponse,
  type UseMarketsAdvancedParams,
  type MarketSortBy,
  type SortOrder,
  type TimeFilter,
} from './use-markets-advanced';

// Watchlist hooks (PRD #5)
export {
  useWatchlist,
  useAddToWatchlist,
  useRemoveFromWatchlist,
  type WatchlistItem,
  type WatchlistResponse,
} from './use-watchlist';

// Tags hooks (PRD #5)
export {
  useTags,
  type Tag,
  type TagsResponse,
  type TagSortBy,
  type UseTagsParams,
} from './use-tags';

// Trader hooks (Sprint 03 - ClickHouse/FastAPI)
export {
  useTraders,
  useTrader,
  useTraderTrades,
  type Trader,
  type TraderDetail,
  type TraderPosition,
  type TraderListResponse,
  type Trade,
  type TradeListResponse,
  type UseTradersParams,
  type UseTraderTradesParams,
  type TraderSortBy,
} from './use-traders';

// Leaderboard hooks (Sprint 03 - ClickHouse/FastAPI)
export {
  useLeaderboard,
  type LeaderboardEntry,
  type LeaderboardResponse,
  type LeaderboardPeriod,
  type UseLeaderboardParams,
} from './use-leaderboard';

// Smart trades and scores hooks (Sprint 03 - ClickHouse/FastAPI)
export {
  useSmartTrades,
  useWhaleTrades,
  useSmartScores,
  type SmartTrade,
  type WhaleTrade,
  type SmartScore,
  type SmartScoreComponents,
  type SmartScoreListResponse,
  type SmartScoreTimeWindow,
  type UseSmartTradesParams,
  type UseWhaleTradesParams,
  type UseSmartScoresParams,
} from './use-smart-trades';

// Notification hooks
export {
  useNotifications,
  type NotificationOptions,
  type UseNotificationsReturn,
} from './useNotifications';

// Tracked traders hooks (Sprint 04 - User Features)
export {
  useTrackedTraders,
  useTrackedTrader,
  useAddTrackedTrader,
  useRemoveTrackedTrader,
  useUpdateTrackedTrader,
  useTrackedTradersActivity,
  type TrackedTrader,
  type TrackedTraderWithStats,
  type TrackedTradersResponse,
  type TrackedTraderActivity,
  type TrackedTraderTrade,
  type AddTrackedTraderRequest,
  type UpdateTrackedTraderRequest,
  type ActivityFilters,
} from './use-tracked-traders';

// Polymarket proxy hooks (Sprint 00 - Polymarket Proxy Layer)
export {
  useTimeseries,
  useOrderbook,
  useMarketTrades,
  useMarketPrice,
  useTopHolders,
  useMarketTokens,
  type PricePoint,
  type PriceHistoryResponse,
  type TimeseriesInterval,
  type OrderLevel,
  type OrderBookResponse,
  type Trade as ProxyTrade,
  type RecentTradesResponse,
  type TradeSide,
  type TokenPrice,
  type MarketInfoResponse,
  type TopHolder,
  type TopHoldersResponse,
  type TokenInfo,
  type MarketTokensResponse,
  type UseTimeseriesParams,
  type UseOrderbookParams,
  type UseMarketTradesParams,
  type UseMarketPriceParams,
  type UseTopHoldersParams,
  type UseMarketTokensParams,
} from './use-polymarket-proxy';
