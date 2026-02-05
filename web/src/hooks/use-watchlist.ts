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
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

/**
 * Watchlist item returned by the API
 */
export interface WatchlistItem {
  id: string;
  marketId: string;
  polymarketId: string;
  question: string;
  slug: string | null;
  createdAt: string;
}

/**
 * Response type for GET /api/watchlist
 */
export interface WatchlistResponse {
  watchlist: WatchlistItem[];
  marketIds: string[];
}

/**
 * Response type for POST /api/watchlist
 */
export interface AddWatchlistResponse {
  watchlist: WatchlistItem;
}

/**
 * Response type for DELETE /api/watchlist/[marketId]
 */
export interface RemoveWatchlistResponse {
  success: boolean;
  marketId: string;
}

/**
 * Fetch user's watchlist from the API
 */
async function fetchWatchlist(): Promise<WatchlistResponse> {
  const response = await fetch('/api/watchlist');

  if (response.status === 401) {
    // Return empty watchlist for unauthenticated users
    return { watchlist: [], marketIds: [] };
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to fetch watchlist: ${response.status}`);
  }

  return response.json();
}

/**
 * Add a market to watchlist
 */
async function addToWatchlist(marketId: string): Promise<AddWatchlistResponse> {
  const response = await fetch('/api/watchlist', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ marketId }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to add to watchlist: ${response.status}`);
  }

  return response.json();
}

/**
 * Remove a market from watchlist
 */
async function removeFromWatchlist(marketId: string): Promise<RemoveWatchlistResponse> {
  const response = await fetch(`/api/watchlist/${encodeURIComponent(marketId)}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to remove from watchlist: ${response.status}`);
  }

  return response.json();
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
 * data?.watchlist.forEach(item => {
 *   console.log(item.question);
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
        queryClient.setQueryData<WatchlistResponse>(['watchlist'], {
          watchlist: [
            ...previousWatchlist.watchlist,
            {
              id: `temp-${marketId}`,
              marketId,
              polymarketId: '',
              question: '',
              slug: null,
              createdAt: new Date().toISOString(),
            },
          ],
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
          watchlist: previousWatchlist.watchlist.filter((item) => item.marketId !== marketId),
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
