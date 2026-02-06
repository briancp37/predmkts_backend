/**
 * React Query hooks for tracked traders functionality
 *
 * Provides:
 * - useTrackedTraders() - Fetch user's tracked traders with stats
 * - useTrackedTrader() - Fetch single tracked trader details
 * - useAddTrackedTrader() - Add a trader to tracked list (mutation)
 * - useRemoveTrackedTrader() - Remove a trader from tracked list (mutation)
 * - useUpdateTrackedTrader() - Update a tracked trader (mutation)
 * - useTrackedTradersActivity() - Fetch activity feed from tracked traders
 *
 * Features:
 * - Optimistic updates for instant UI feedback
 * - Automatic cache invalidation
 * - Error rollback on mutation failure
 * - Tier limit handling (FREE=6, PRO=50)
 * - Calls FastAPI backend /api/v1/tracked-traders endpoints
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest, ApiError, getAccessToken } from '@/lib/api/client';

/**
 * Trade record from the activity feed
 */
export interface TrackedTraderTrade {
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
 * Base tracked trader schema
 */
export interface TrackedTrader {
  id: string;
  traderAddress: string;
  customName: string | null;
  createdAt: string;
}

/**
 * Tracked trader with stats from ClickHouse
 */
export interface TrackedTraderWithStats extends TrackedTrader {
  totalPnl: number;
  recentTrades: number;
  smartScore: number | null;
}

/**
 * Response type for GET /api/v1/tracked-traders
 */
export interface TrackedTradersResponse {
  items: TrackedTraderWithStats[];
  count: number;
  /** Tier limit for tracked traders */
  limit: number;
}

/**
 * Activity feed item for a tracked trader
 */
export interface TrackedTraderActivity {
  traderId: string;
  traderAddress: string;
  customName: string | null;
  trade: TrackedTraderTrade;
  timestamp: string;
}

/**
 * Request body for adding a tracked trader
 */
export interface AddTrackedTraderRequest {
  traderAddress: string;
  customName?: string | null;
}

/**
 * Request body for updating a tracked trader
 */
export interface UpdateTrackedTraderRequest {
  customName?: string | null;
}

/**
 * Activity feed filter options
 */
export interface ActivityFilters {
  limit?: number;
  startDate?: string;
  endDate?: string;
}

/**
 * Fetch user's tracked traders from the API
 */
async function fetchTrackedTraders(): Promise<TrackedTradersResponse> {
  // Return empty list if not authenticated
  if (!getAccessToken()) {
    return { items: [], count: 0, limit: 6 };
  }

  try {
    return await apiRequest<TrackedTradersResponse>('/tracked-traders');
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return { items: [], count: 0, limit: 6 };
    }
    throw error;
  }
}

/**
 * Fetch a single tracked trader by ID
 */
async function fetchTrackedTrader(trackerId: string): Promise<TrackedTraderWithStats> {
  return apiRequest<TrackedTraderWithStats>(`/tracked-traders/${encodeURIComponent(trackerId)}`);
}

/**
 * Add a trader to tracked list
 */
async function addTrackedTrader(request: AddTrackedTraderRequest): Promise<TrackedTrader> {
  return apiRequest<TrackedTrader>('/tracked-traders', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Remove a trader from tracked list
 */
async function removeTrackedTrader(trackerId: string): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    throw new ApiError('Not authenticated', 401, 'Please log in');
  }

  const response = await fetch(`/api/v1/tracked-traders/${encodeURIComponent(trackerId)}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new ApiError('Tracked trader not found', 404, 'Tracked trader not found');
    }
    const error = await response.json().catch(() => ({}));
    throw new ApiError(error.detail || 'Failed to remove tracked trader', response.status, error.detail);
  }

  // 204 No Content - success
}

/**
 * Update a tracked trader's custom name
 */
async function updateTrackedTrader(
  trackerId: string,
  request: UpdateTrackedTraderRequest
): Promise<TrackedTrader> {
  return apiRequest<TrackedTrader>(`/tracked-traders/${encodeURIComponent(trackerId)}`, {
    method: 'PATCH',
    body: JSON.stringify(request),
  });
}

/**
 * Fetch activity feed from tracked traders
 */
async function fetchTrackedTradersActivity(filters: ActivityFilters = {}): Promise<TrackedTraderActivity[]> {
  if (!getAccessToken()) {
    return [];
  }

  const params = new URLSearchParams();
  if (filters.limit) params.set('limit', String(filters.limit));
  if (filters.startDate) params.set('startDate', filters.startDate);
  if (filters.endDate) params.set('endDate', filters.endDate);

  const queryString = params.toString();
  const endpoint = `/tracked-traders/activity${queryString ? `?${queryString}` : ''}`;

  try {
    return await apiRequest<TrackedTraderActivity[]>(endpoint);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return [];
    }
    throw error;
  }
}

/**
 * Hook to fetch user's tracked traders with stats
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useTrackedTraders();
 *
 * // Check if at tier limit
 * const atLimit = data?.count >= data?.limit;
 *
 * // List all tracked traders
 * data?.items.forEach(trader => {
 *   console.log(trader.traderAddress, trader.totalPnl);
 * });
 * ```
 */
export function useTrackedTraders(options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: ['tracked-traders'],
    queryFn: fetchTrackedTraders,
    enabled,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to fetch a single tracked trader with stats
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useTrackedTrader(trackerId);
 *
 * console.log(data?.totalPnl, data?.smartScore);
 * ```
 */
export function useTrackedTrader(trackerId: string, options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: ['tracked-traders', trackerId],
    queryFn: () => fetchTrackedTrader(trackerId),
    enabled: enabled && !!trackerId,
    staleTime: 60 * 1000,
  });
}

/**
 * Hook to add a trader to tracked list with optimistic updates
 *
 * @example
 * ```tsx
 * const { mutate: addTrader, isPending } = useAddTrackedTrader();
 *
 * addTrader(
 *   { traderAddress: '0x123...', customName: 'Whale #1' },
 *   {
 *     onSuccess: () => console.log('Added!'),
 *     onError: (error) => {
 *       if (error.status === 403) {
 *         // Tier limit exceeded
 *         console.log('Upgrade to add more traders');
 *       }
 *     },
 *   }
 * );
 * ```
 */
export function useAddTrackedTrader() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: addTrackedTrader,
    // Optimistic update
    onMutate: async (request: AddTrackedTraderRequest) => {
      await queryClient.cancelQueries({ queryKey: ['tracked-traders'] });

      const previousData = queryClient.getQueryData<TrackedTradersResponse>(['tracked-traders']);

      if (previousData) {
        const optimisticTrader: TrackedTraderWithStats = {
          id: `temp-${request.traderAddress}`,
          traderAddress: request.traderAddress.toLowerCase(),
          customName: request.customName ?? null,
          createdAt: new Date().toISOString(),
          totalPnl: 0,
          recentTrades: 0,
          smartScore: null,
        };

        queryClient.setQueryData<TrackedTradersResponse>(['tracked-traders'], {
          items: [...previousData.items, optimisticTrader],
          count: previousData.count + 1,
          limit: previousData.limit,
        });
      }

      return { previousData };
    },
    onError: (_err, _request, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(['tracked-traders'], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-traders'] });
    },
  });
}

/**
 * Hook to remove a trader from tracked list with optimistic updates
 *
 * @example
 * ```tsx
 * const { mutate: removeTrader, isPending } = useRemoveTrackedTrader();
 *
 * removeTrader(trackerId, {
 *   onSuccess: () => console.log('Removed!'),
 *   onError: (error) => console.error(error),
 * });
 * ```
 */
export function useRemoveTrackedTrader() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: removeTrackedTrader,
    onMutate: async (trackerId: string) => {
      await queryClient.cancelQueries({ queryKey: ['tracked-traders'] });

      const previousData = queryClient.getQueryData<TrackedTradersResponse>(['tracked-traders']);

      if (previousData) {
        queryClient.setQueryData<TrackedTradersResponse>(['tracked-traders'], {
          items: previousData.items.filter((t) => t.id !== trackerId),
          count: previousData.count - 1,
          limit: previousData.limit,
        });
      }

      return { previousData };
    },
    onError: (_err, _trackerId, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(['tracked-traders'], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-traders'] });
    },
  });
}

/**
 * Hook to update a tracked trader's custom name
 *
 * @example
 * ```tsx
 * const { mutate: updateTrader, isPending } = useUpdateTrackedTrader();
 *
 * updateTrader(
 *   { trackerId: '123', customName: 'New Name' },
 *   { onSuccess: () => console.log('Updated!') }
 * );
 * ```
 */
export function useUpdateTrackedTrader() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ trackerId, ...request }: { trackerId: string } & UpdateTrackedTraderRequest) =>
      updateTrackedTrader(trackerId, request),
    onMutate: async ({ trackerId, customName }) => {
      await queryClient.cancelQueries({ queryKey: ['tracked-traders'] });

      const previousData = queryClient.getQueryData<TrackedTradersResponse>(['tracked-traders']);

      if (previousData) {
        queryClient.setQueryData<TrackedTradersResponse>(['tracked-traders'], {
          ...previousData,
          items: previousData.items.map((t) =>
            t.id === trackerId ? { ...t, customName: customName ?? null } : t
          ),
        });
      }

      return { previousData };
    },
    onError: (_err, _request, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(['tracked-traders'], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-traders'] });
    },
  });
}

/**
 * Hook to fetch activity feed from tracked traders
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useTrackedTradersActivity({
 *   limit: 50,
 *   startDate: '2024-01-01',
 * });
 *
 * data?.forEach(activity => {
 *   console.log(activity.customName, activity.trade.marketQuestion);
 * });
 * ```
 */
export function useTrackedTradersActivity(filters?: ActivityFilters, options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: ['tracked-traders-activity', filters],
    queryFn: () => fetchTrackedTradersActivity(filters),
    enabled,
    staleTime: 30 * 1000, // 30 seconds - activity updates more frequently
  });
}
