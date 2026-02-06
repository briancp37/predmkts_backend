/**
 * Markets Page
 *
 * PRD #12 (Sprint 9) - Create Markets page with all components integrated
 * PRD #18 - Performance optimizations (lazy loading, suspense)
 *
 * Features:
 * - MarketFilters component with comprehensive filter controls
 * - Card and Table view toggle
 * - Pagination with per-page selector
 * - Tags modal for tag filtering (lazy loaded)
 * - Watchlist functionality for authenticated users
 * - Loading states with skeleton loaders
 * - Empty state when no markets match filters
 * - React.memo optimized components
 */

'use client';

import { useState, useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { LayoutGrid } from 'lucide-react';
import { useSession } from '@/components/providers';
import {
  useMarketsAdvanced,
  useWatchlist,
  useAddToWatchlist,
  useRemoveFromWatchlist,
} from '@/hooks';
import {
  MarketFilters,
  MarketCard,
  MarketTable,
  ViewToggle,
  MarketsPagination,
  DEFAULT_FILTER_VALUES,
  type MarketFilterValues,
  type ViewMode,
  type PerPageOption,
} from '@/components/markets';

// Lazy load TagsModal component - PRD #18 performance optimization
const TagsModal = dynamic(
  () => import('@/components/markets/tags-modal').then((mod) => ({ default: mod.TagsModal })),
  {
    loading: () => null, // No loading state needed as modal opens on demand
    ssr: false, // Disable SSR for modal
  }
);

/**
 * Convert filter values to API params
 * Handles the conversion from UI filter state to API query parameters
 */
function buildApiParams(
  filters: MarketFilterValues,
  page: number,
  perPage: PerPageOption
) {
  const params: Parameters<typeof useMarketsAdvanced>[0] = {
    category: filters.category || undefined,
    sortBy: filters.sortBy,
    sortOrder: filters.sortOrder,
    page,
    limit: perPage,
  };

  // Volume filters
  if (filters.minVolume) {
    params.minVolume = parseFloat(filters.minVolume);
  }
  if (filters.maxVolume) {
    params.maxVolume = parseFloat(filters.maxVolume);
  }

  // Liquidity filters
  if (filters.minLiquidity) {
    params.minLiquidity = parseFloat(filters.minLiquidity);
  }
  if (filters.maxLiquidity) {
    params.maxLiquidity = parseFloat(filters.maxLiquidity);
  }

  // Spread percentage filters
  if (filters.minSpread) {
    params.minSpread = parseFloat(filters.minSpread);
  }
  if (filters.maxSpread) {
    params.maxSpread = parseFloat(filters.maxSpread);
  }

  // Spread cents filters
  if (filters.minSpreadCents) {
    params.minSpreadCents = parseFloat(filters.minSpreadCents);
  }
  if (filters.maxSpreadCents) {
    params.maxSpreadCents = parseFloat(filters.maxSpreadCents);
  }

  // Time filters
  if (filters.timeRemaining !== 'all') {
    params.timeRemaining = filters.timeRemaining;
  }
  if (filters.createdDate !== 'all') {
    params.createdDate = filters.createdDate;
  }

  // Change filters based on change option
  if (filters.change === 'under10') {
    params.maxChange = 10;
  } else if (filters.change === 'over10') {
    params.minChange = 10;
  } else if (filters.change === 'over20') {
    params.minChange = 20;
  }

  // Tags filter
  if (filters.tags.length > 0) {
    params.tags = filters.tags.join(',');
  }

  return params;
}

// Import skeleton components
import {
  MarketCardSkeleton,
  MarketTableSkeleton,
  StaleIndicator,
} from '@/components/loading-skeleton';

export default function MarketsPage() {
  // Authentication state
  const { data: session, status: authStatus } = useSession();
  const isAuthenticated = authStatus === 'authenticated' && !!session?.user;

  // Filter state
  const [filters, setFilters] = useState<MarketFilterValues>(DEFAULT_FILTER_VALUES);

  // View mode state
  const [viewMode, setViewMode] = useState<ViewMode>('card');

  // Pagination state
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState<PerPageOption>(25);

  // Tags modal state
  const [isTagsModalOpen, setIsTagsModalOpen] = useState(false);

  // Watchlist hooks
  const { data: watchlistData } = useWatchlist({ enabled: isAuthenticated });
  const { mutate: addToWatchlist, isPending: isAddPending, variables: addingMarketId } = useAddToWatchlist();
  const { mutate: removeFromWatchlist, isPending: isRemovePending, variables: removingMarketId } = useRemoveFromWatchlist();

  // Track pending watchlist operations per market
  const pendingWatchlistId = isAddPending ? addingMarketId : isRemovePending ? removingMarketId : null;

  // Build watchlist IDs set for quick lookup
  const watchlistedIds = useMemo(() => {
    return new Set(watchlistData?.marketIds ?? []);
  }, [watchlistData?.marketIds]);

  // Build API params from filter state
  const apiParams = useMemo(() => {
    return buildApiParams(filters, page, perPage);
  }, [filters, page, perPage]);

  // Fetch markets
  const {
    data: marketsData,
    isLoading: isLoadingMarkets,
    isFetching: isFetchingMarkets,
  } = useMarketsAdvanced(apiParams);

  // Filter markets by watchlist if watchlistOnly is enabled
  const displayedMarkets = useMemo(() => {
    if (!marketsData?.items) return [];
    if (!filters.watchlistOnly) return marketsData.items;
    return marketsData.items.filter((market) => watchlistedIds.has(market.id));
  }, [marketsData?.items, filters.watchlistOnly, watchlistedIds]);

  // Adjusted total for watchlist filtering
  const displayedTotal = filters.watchlistOnly
    ? displayedMarkets.length
    : (marketsData?.total ?? 0);

  // Handle filter changes - reset to page 1
  const handleFilterChange = useCallback((newFilters: MarketFilterValues) => {
    setFilters(newFilters);
    setPage(1);
  }, []);

  // Handle watchlist toggle
  const handleWatchlistToggle = useCallback(
    (marketId: string) => {
      if (!isAuthenticated) return;

      if (watchlistedIds.has(marketId)) {
        removeFromWatchlist(marketId);
      } else {
        addToWatchlist(marketId);
      }
    },
    [isAuthenticated, watchlistedIds, addToWatchlist, removeFromWatchlist]
  );

  // Handle tags modal apply
  const handleTagsApply = useCallback(
    (tags: string[]) => {
      handleFilterChange({ ...filters, tags });
    },
    [filters, handleFilterChange]
  );

  // Handle page change
  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
    // Scroll to top of page
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  // Handle per-page change (also resets page via the component)
  const handlePerPageChange = useCallback((newPerPage: PerPageOption) => {
    setPerPage(newPerPage);
  }, []);

  const isLoading = isLoadingMarkets;
  const isFetching = isFetchingMarkets && !isLoading;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <LayoutGrid className="h-8 w-8 text-indigo-600" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Markets</h1>
          <p className="text-gray-500">
            Browse and filter prediction markets with real-time bid/ask data
          </p>
        </div>
      </div>

      {/* Filters */}
      <MarketFilters
        values={filters}
        onChange={handleFilterChange}
        onTagsClick={() => setIsTagsModalOpen(true)}
        selectedTagsCount={filters.tags.length}
        isAuthenticated={isAuthenticated}
      />

      {/* View Toggle and Results Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <ViewToggle value={viewMode} onChange={setViewMode} />
          {marketsData && !isLoading && (
            <span className="text-sm text-gray-500 flex items-center gap-2">
              <span>{displayedTotal.toLocaleString()} market{displayedTotal !== 1 ? 's' : ''}</span>
              <StaleIndicator isStale={false} isRefetching={isFetching} />
            </span>
          )}
        </div>
      </div>

      {/* Markets Display */}
      {isLoading ? (
        viewMode === 'card' ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <MarketCardSkeleton key={i} />
            ))}
          </div>
        ) : (
          <MarketTableSkeleton rows={10} />
        )
      ) : displayedMarkets.length === 0 ? (
        /* Empty State */
        <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 py-16 text-center">
          <LayoutGrid className="h-12 w-12 text-gray-400" />
          <h3 className="mt-4 text-lg font-medium text-gray-900">No markets found</h3>
          <p className="mt-2 text-sm text-gray-500">
            {filters.watchlistOnly
              ? 'Your watchlist is empty or no watchlisted markets match your filters.'
              : 'Try adjusting your filters to see more results.'}
          </p>
          {(filters.category ||
            filters.minVolume ||
            filters.maxVolume ||
            filters.minLiquidity ||
            filters.maxLiquidity ||
            filters.minSpread ||
            filters.maxSpread ||
            filters.minSpreadCents ||
            filters.maxSpreadCents ||
            filters.timeRemaining !== 'all' ||
            filters.createdDate !== 'all' ||
            filters.change ||
            filters.tags.length > 0 ||
            filters.watchlistOnly) && (
            <button
              type="button"
              onClick={() => handleFilterChange(DEFAULT_FILTER_VALUES)}
              className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Reset Filters
            </button>
          )}
        </div>
      ) : viewMode === 'card' ? (
        /* Card View */
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {displayedMarkets.map((market) => (
            <MarketCard
              key={market.id}
              market={market}
              isWatchlisted={watchlistedIds.has(market.id)}
              isWatchlistPending={pendingWatchlistId === market.id}
              onWatchlistToggle={isAuthenticated ? handleWatchlistToggle : undefined}
            />
          ))}
        </div>
      ) : (
        /* Table View */
        <MarketTable
          markets={displayedMarkets}
          loading={isLoading}
          watchlistedIds={watchlistedIds}
          pendingWatchlistId={pendingWatchlistId}
          onWatchlistToggle={isAuthenticated ? handleWatchlistToggle : undefined}
        />
      )}

      {/* Pagination */}
      {!isLoading && displayedMarkets.length > 0 && (
        <MarketsPagination
          page={page}
          perPage={perPage}
          total={displayedTotal}
          onPageChange={handlePageChange}
          onPerPageChange={handlePerPageChange}
        />
      )}

      {/* Tags Modal */}
      <TagsModal
        isOpen={isTagsModalOpen}
        onClose={() => setIsTagsModalOpen(false)}
        selectedTags={filters.tags}
        onApply={handleTagsApply}
      />
    </div>
  );
}
