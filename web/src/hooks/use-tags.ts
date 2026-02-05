/**
 * React Query hooks for tags functionality
 *
 * PRD #5 - Create React Query hooks for Markets page data fetching
 *
 * Provides:
 * - useTags(search?) - Fetch available market tags with optional search
 */

'use client';

import { useQuery } from '@tanstack/react-query';

/**
 * Tag data returned by the API
 */
export interface Tag {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  marketCount: number;
  createdAt: string;
}

/**
 * Response type for GET /api/tags
 */
export interface TagsResponse {
  tags: Tag[];
  total: number;
}

/**
 * Sort options for tags
 */
export type TagSortBy = 'popular' | 'alphabetical';

/**
 * Query parameters for useTags hook
 */
export interface UseTagsParams {
  /** Search filter for tag names */
  search?: string;
  /** Sort by popularity or alphabetically (default: popular) */
  sort?: TagSortBy;
  /** Maximum number of tags to return (default: 100, max: 500) */
  limit?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch tags from the API
 */
async function fetchTags(params: Omit<UseTagsParams, 'enabled'>): Promise<TagsResponse> {
  const searchParams = new URLSearchParams();

  if (params.search) {
    searchParams.set('search', params.search);
  }
  if (params.sort) {
    searchParams.set('sort', params.sort);
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', String(params.limit));
  }

  const queryString = searchParams.toString();
  const url = `/api/tags${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `Failed to fetch tags: ${response.status}`);
  }

  return response.json();
}

/**
 * Hook to fetch available market tags
 *
 * @example
 * ```tsx
 * // Fetch all tags sorted by popularity
 * const { data, isLoading, error } = useTags();
 *
 * // Search for specific tags
 * const { data } = useTags({ search: 'pol' });
 *
 * // Sort alphabetically
 * const { data } = useTags({ sort: 'alphabetical' });
 *
 * // Access tag data
 * data?.tags.forEach(tag => {
 *   console.log(tag.name, tag.marketCount);
 * });
 * ```
 */
export function useTags(params: UseTagsParams = {}) {
  const { enabled = true, ...queryParams } = params;

  return useQuery({
    queryKey: ['tags', queryParams],
    queryFn: () => fetchTags(queryParams),
    enabled,
    // Tags don't change frequently, longer stale time
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
