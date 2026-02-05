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
 * ```
 */

// Market hooks
export {
  useMarkets,
  useMarket,
  type Market,
  type MarketOutcome,
  type MarketsResponse,
  type UseMarketsParams,
} from './use-markets';

// Advanced market hooks (PRD #5)
export {
  useMarketsAdvanced,
  type AdvancedMarket,
  type AdvancedMarketOutcome,
  type AdvancedMarketsResponse,
  type UseMarketsAdvancedParams,
  type MarketSortBy,
  type SortOrder,
  type TimeFilter,
  type PaginationMeta,
} from './use-markets-advanced';

// Watchlist hooks (PRD #5)
export {
  useWatchlist,
  useAddToWatchlist,
  useRemoveFromWatchlist,
  type WatchlistItem,
  type WatchlistResponse,
  type AddWatchlistResponse,
  type RemoveWatchlistResponse,
} from './use-watchlist';

// Tags hooks (PRD #5)
export {
  useTags,
  type Tag,
  type TagsResponse,
  type TagSortBy,
  type UseTagsParams,
} from './use-tags';

// Trader hooks
export {
  useTrader,
  useTraderTrades,
  type Trader,
  type TraderPosition,
  type Trade,
  type TraderTradesResponse,
  type UseTraderTradesParams,
  type PositionMarket,
  type PositionOutcome,
  type TradeMarket,
  type TradeOutcome,
} from './use-traders';

// Notification hooks
export {
  useNotifications,
  type NotificationOptions,
  type UseNotificationsReturn,
} from './useNotifications';
