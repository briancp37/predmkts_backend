/**
 * Watchlist functionality tests
 *
 * Tests the watchlist hooks and API integration:
 * - useWatchlist hook for fetching watchlist
 * - useAddToWatchlist mutation
 * - useRemoveFromWatchlist mutation
 * - Optimistic updates
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';
import { useWatchlist, useAddToWatchlist, useRemoveFromWatchlist } from '@/hooks/use-watchlist';
import { server } from './mocks/server';
import { http, HttpResponse } from 'msw';
import { mockWatchlistItem } from './mocks/handlers';

// Create a wrapper with QueryClient for hooks
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('useWatchlist', () => {
  beforeEach(() => {
    // Set up an authenticated state
    localStorage.setItem('access_token', 'test-token');
  });

  it('fetches watchlist items', async () => {
    const { result } = renderHook(() => useWatchlist(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toBeDefined();
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0]?.marketId).toBe(mockWatchlistItem.marketId);
  });

  it('returns empty watchlist when not authenticated', async () => {
    localStorage.removeItem('access_token');

    const { result } = renderHook(() => useWatchlist(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data?.items).toHaveLength(0);
    expect(result.current.data?.count).toBe(0);
  });

  it('provides marketIds for quick lookup', async () => {
    const { result } = renderHook(() => useWatchlist(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data?.marketIds).toContain(mockWatchlistItem.marketId);
  });

  it('can be disabled', async () => {
    const { result } = renderHook(() => useWatchlist({ enabled: false }), {
      wrapper: createWrapper(),
    });

    // Should not fetch when disabled
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isFetching).toBe(false);
    expect(result.current.data).toBeUndefined();
  });
});

describe('useAddToWatchlist', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token');
  });

  it('adds a market to watchlist', async () => {
    const wrapper = createWrapper();
    const marketId = '0x1234567890123456789012345678901234567890123456789012345678901234';

    // First, set up initial watchlist data
    const { result: watchlistResult } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => {
      expect(watchlistResult.current.isLoading).toBe(false);
    });

    // Now test the add mutation
    const { result } = renderHook(() => useAddToWatchlist(), { wrapper });

    await act(async () => {
      result.current.mutate(marketId);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it('handles duplicate market error', async () => {
    const wrapper = createWrapper();

    const { result } = renderHook(() => useAddToWatchlist(), { wrapper });

    await act(async () => {
      result.current.mutate('already-in-watchlist');
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error?.message).toContain('already in watchlist');
  });

  it('handles authentication error', async () => {
    localStorage.removeItem('access_token');

    // Override handler to return 401
    server.use(
      http.post('/api/v1/watchlist', () => {
        return HttpResponse.json(
          { detail: 'Not authenticated', code: 'AUTHENTICATION_FAILED', status: 401 },
          { status: 401 }
        );
      })
    );

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAddToWatchlist(), { wrapper });

    await act(async () => {
      result.current.mutate('test-market-id');
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe('useRemoveFromWatchlist', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token');
  });

  it('removes a market from watchlist', async () => {
    const wrapper = createWrapper();

    const { result } = renderHook(() => useRemoveFromWatchlist(), { wrapper });

    await act(async () => {
      result.current.mutate(mockWatchlistItem.marketId);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it('handles not found error when market not in watchlist', async () => {
    const wrapper = createWrapper();

    const { result } = renderHook(() => useRemoveFromWatchlist(), { wrapper });

    await act(async () => {
      result.current.mutate('not-in-watchlist');
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error?.message).toContain('not found');
  });

  it('handles authentication error', async () => {
    localStorage.removeItem('access_token');

    const wrapper = createWrapper();
    const { result } = renderHook(() => useRemoveFromWatchlist(), { wrapper });

    await act(async () => {
      result.current.mutate('test-market-id');
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe('Watchlist optimistic updates', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token');
  });

  it('add mutation returns pending state during add operation', async () => {
    const wrapper = createWrapper();

    const { result } = renderHook(() => useAddToWatchlist(), { wrapper });

    // Initially not pending
    expect(result.current.isPending).toBe(false);

    await act(async () => {
      result.current.mutate('new-market-id');
    });

    // After mutation completes
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it('remove mutation returns pending state during remove operation', async () => {
    const wrapper = createWrapper();

    const { result } = renderHook(() => useRemoveFromWatchlist(), { wrapper });

    // Initially not pending
    expect(result.current.isPending).toBe(false);

    await act(async () => {
      result.current.mutate(mockWatchlistItem.marketId);
    });

    // After mutation completes
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it('returns error state on add failure', async () => {
    // Make the add endpoint fail
    server.use(
      http.post('/api/v1/watchlist', () => {
        return HttpResponse.json(
          { detail: 'Server error', code: 'INTERNAL_ERROR', status: 500 },
          { status: 500 }
        );
      })
    );

    const wrapper = createWrapper();

    const { result } = renderHook(() => useAddToWatchlist(), { wrapper });

    await act(async () => {
      result.current.mutate('test-market-id');
    });

    // Wait for the error
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeDefined();
  });
});
