/**
 * React Query hooks for watchlist functionality
 *
 * PRD #5 - Create React Query hooks for Markets page data fetching
 *
 * Provides:
 * - useWatchlist() - Fetch user's watchlist
 * - useAddToWatchlist() - Add a market to watchlist (mutation)
 * - useRemoveFromWatchlist() - Remove a market from watchlist (mutation)
 *
 * Features:
 * - Optimistic updates for instant UI feedback
 * - Automatic cache invalidation
 * - Error rollback on mutation failure
 * - Calls FastAPI backend /api/v1/watchlist endpoints
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest, ApiError, getAccessToken } from '@/lib/api/client';

/**
 * Watchlist item with market details from the API
 */
export interface WatchlistItem {
  id: string;
  marketId: string;
  createdAt: string;
  marketQuestion: string;
  marketCategory: string | null;
  currentPrice: number;
  priceChange24h: number;
  resolved: boolean;
}

/**
 * Response type for GET /api/v1/watchlist
 */
export interface WatchlistResponse {
  items: WatchlistItem[];
  count: number;
  /** Derived from items for quick lookup */
  marketIds: string[];
}

/**
 * Internal API response type (before we add marketIds)
 */
interface WatchlistApiResponse {
  items: WatchlistItem[];
  count: number;
}

/**
 * Fetch user's watchlist from the API
 */
async function fetchWatchlist(): Promise<WatchlistResponse> {
  // Return empty watchlist if not authenticated
  if (!getAccessToken()) {
    return { items: [], count: 0, marketIds: [] };
  }

  try {
    const response = await apiRequest<WatchlistApiResponse>('/watchlist');
    return {
      ...response,
      marketIds: response.items.map((item) => item.marketId),
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      // Return empty watchlist for unauthenticated users
      return { items: [], count: 0, marketIds: [] };
    }
    throw error;
  }
}

/**
 * Add a market to watchlist
 */
async function addToWatchlist(marketId: string): Promise<{ id: string; marketId: string; createdAt: string }> {
  return apiRequest<{ id: string; marketId: string; createdAt: string }>('/watchlist', {
    method: 'POST',
    body: JSON.stringify({ marketId }),
  });
}

/**
 * Remove a market from watchlist
 * Note: Returns void since the API returns 204 No Content
 */
async function removeFromWatchlist(marketId: string): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    throw new ApiError('Not authenticated', 401, 'Please log in');
  }

  const response = await fetch(`/api/v1/watchlist/${encodeURIComponent(marketId)}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new ApiError('Market not found in watchlist', 404, 'Market not found in watchlist');
    }
    const error = await response.json().catch(() => ({}));
    throw new ApiError(error.detail || 'Failed to remove from watchlist', response.status, error.detail);
  }

  // 204 No Content - success, nothing to return
}

/**
 * Hook to fetch user's watchlist
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useWatchlist();
 *
 * // Check if a market is in the watchlist
 * const isWatchlisted = data?.marketIds.includes(marketId);
 *
 * // List all watchlisted markets
 * data?.items.forEach(item => {
 *   console.log(item.marketQuestion);
 * });
 * ```
 */
export function useWatchlist(options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: ['watchlist'],
    queryFn: fetchWatchlist,
    enabled,
    // Keep data fresh but not too aggressive
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to add a market to watchlist with optimistic updates
 *
 * @example
 * ```tsx
 * const { mutate: addToWatchlist, isPending } = useAddToWatchlist();
 *
 * // Add market to watchlist
 * addToWatchlist(marketId, {
 *   onSuccess: () => console.log('Added!'),
 *   onError: (error) => console.error(error),
 * });
 * ```
 */
export function useAddToWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: addToWatchlist,
    // Optimistic update
    onMutate: async (marketId: string) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['watchlist'] });

      // Snapshot the previous value
      const previousWatchlist = queryClient.getQueryData<WatchlistResponse>(['watchlist']);

      // Optimistically update the cache
      if (previousWatchlist) {
        const newItem: WatchlistItem = {
          id: `temp-${marketId}`,
          marketId,
          marketQuestion: '',
          marketCategory: null,
          currentPrice: 0,
          priceChange24h: 0,
          resolved: false,
          createdAt: new Date().toISOString(),
        };
        queryClient.setQueryData<WatchlistResponse>(['watchlist'], {
          items: [...previousWatchlist.items, newItem],
          count: previousWatchlist.count + 1,
          marketIds: [...previousWatchlist.marketIds, marketId],
        });
      }

      // Return context with previous value
      return { previousWatchlist };
    },
    // If the mutation fails, roll back to the previous value
    onError: (_err, _marketId, context) => {
      if (context?.previousWatchlist) {
        queryClient.setQueryData(['watchlist'], context.previousWatchlist);
      }
    },
    // Always refetch after error or success
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });
}

/**
 * Hook to remove a market from watchlist with optimistic updates
 *
 * @example
 * ```tsx
 * const { mutate: removeFromWatchlist, isPending } = useRemoveFromWatchlist();
 *
 * // Remove market from watchlist
 * removeFromWatchlist(marketId, {
 *   onSuccess: () => console.log('Removed!'),
 *   onError: (error) => console.error(error),
 * });
 * ```
 */
export function useRemoveFromWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: removeFromWatchlist,
    // Optimistic update
    onMutate: async (marketId: string) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['watchlist'] });

      // Snapshot the previous value
      const previousWatchlist = queryClient.getQueryData<WatchlistResponse>(['watchlist']);

      // Optimistically update the cache
      if (previousWatchlist) {
        queryClient.setQueryData<WatchlistResponse>(['watchlist'], {
          items: previousWatchlist.items.filter((item) => item.marketId !== marketId),
          count: previousWatchlist.count - 1,
          marketIds: previousWatchlist.marketIds.filter((id) => id !== marketId),
        });
      }

      // Return context with previous value
      return { previousWatchlist };
    },
    // If the mutation fails, roll back to the previous value
    onError: (_err, _marketId, context) => {
      if (context?.previousWatchlist) {
        queryClient.setQueryData(['watchlist'], context.previousWatchlist);
      }
    },
    // Always refetch after error or success
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });
}
