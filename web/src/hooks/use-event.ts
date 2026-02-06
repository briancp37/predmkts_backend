/**
 * React Query hooks for event data fetching
 *
 * Calls FastAPI backend at /api/v1/events
 *
 * Provides:
 * - useEvent(slug) - Fetch single event by slug or platform_event_id
 * - useEvents() - Fetch events with filtering and pagination
 */

'use client';

import { useQuery } from '@tanstack/react-query';
import type { components } from '@/lib/api/schema';

const API_BASE = '/api/v1';

// Re-export schema types for convenience
export type EventResponse = components['schemas']['EventResponse'];
export type EventMarketResponse = components['schemas']['EventMarketResponse'];
export type EventMarketOutcome = components['schemas']['EventMarketOutcome'];
export type EventListResponse = components['schemas']['EventListResponse'];

/**
 * Query parameters for useEvents hook
 */
export interface UseEventsParams {
  /** Filter by category (exact match) */
  category?: string;
  /** Search in title and description (case-insensitive) */
  search?: string;
  /** Filter by status (e.g., 'active', 'resolved') */
  status?: string;
  /** Number of results (default: 50, max: 500) */
  limit?: number;
  /** Pagination offset (default: 0) */
  offset?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch a single event from the FastAPI backend
 */
async function fetchEvent(eventId: string): Promise<EventResponse> {
  const response = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}`);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Event not found');
    }
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch event: ${response.status}`);
  }

  return response.json();
}

/**
 * Fetch events from the API
 */
async function fetchEvents(params: Omit<UseEventsParams, 'enabled'>): Promise<EventListResponse> {
  const searchParams = new URLSearchParams();

  if (params.category) {
    searchParams.set('category', params.category);
  }
  if (params.search) {
    searchParams.set('search', params.search);
  }
  if (params.status) {
    searchParams.set('status', params.status);
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }
  if (params.offset !== undefined) {
    searchParams.set('offset', String(params.offset));
  }

  const queryString = searchParams.toString();
  const url = `${API_BASE}/events${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch events: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch a single event by slug or platform_event_id
 *
 * @example
 * ```tsx
 * // Fetch by slug from URL params
 * const { data: event, isLoading, error } = useEvent(params.slug);
 *
 * // Fetch by platform event ID
 * const { data: event } = useEvent('12345');
 *
 * // Disable query until ready
 * const { data } = useEvent(selectedId, { enabled: !!selectedId });
 * ```
 */
export function useEvent(
  eventId: string | undefined | null,
  options?: { enabled?: boolean }
) {
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: ['event', eventId],
    queryFn: () => fetchEvent(eventId!),
    enabled: enabled && !!eventId,
  });
}

/**
 * Hook to fetch events with filtering and pagination
 *
 * @example
 * ```tsx
 * // Fetch all events
 * const { data, isLoading, error } = useEvents();
 *
 * // Fetch with filters
 * const { data } = useEvents({
 *   search: 'election',
 *   category: 'Politics',
 *   status: 'active',
 *   limit: 20,
 * });
 *
 * // Paginate
 * const { data } = useEvents({ offset: 50 });
 * ```
 */
export function useEvents(params: UseEventsParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['events', queryParams],
    queryFn: () => fetchEvents(queryParams),
    enabled,
  });
}
