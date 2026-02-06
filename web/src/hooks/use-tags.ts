/**
 * React Query hooks for tags functionality
 *
 * Sprint 05 - Updated to use FastAPI backend at /api/v1/markets/tags
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
  marketCount: number;
}

/**
 * Response type for useTags hook
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
  /** Search filter for tag names (client-side filtering) */
  search?: string;
  /** Sort by popularity or alphabetically (default: popular) */
  sort?: TagSortBy;
  /** Maximum number of tags to return (default: 100, max: 500) */
  limit?: number;
  /** Enable/disable the query (default: true) */
  enabled?: boolean;
}

/**
 * Fetch tags from the FastAPI backend
 */
async function fetchTags(): Promise<Tag[]> {
  const response = await fetch('/api/v1/markets/tags');

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch tags: ${response.status}`);
  }

  return response.json();
}

/**
 * Apply client-side filtering and sorting to tags
 */
function processTagsClientSide(
  tags: Tag[],
  params: Omit<UseTagsParams, 'enabled'>
): TagsResponse {
  let result = [...tags];

  // Apply search filter (client-side)
  if (params.search) {
    const searchLower = params.search.toLowerCase();
    result = result.filter(
      (tag) =>
        tag.name.toLowerCase().includes(searchLower) ||
        tag.slug.toLowerCase().includes(searchLower)
    );
  }

  // Apply sorting
  if (params.sort === 'alphabetical') {
    result.sort((a, b) => a.name.localeCompare(b.name));
  }
  // 'popular' sort is default from API (by marketCount desc)

  // Apply limit
  if (params.limit !== undefined) {
    result = result.slice(0, params.limit);
  }

  return {
    tags: result,
    total: result.length,
  };
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
    queryKey: ['tags'],
    queryFn: fetchTags,
    enabled,
    // Tags don't change frequently, longer stale time
    staleTime: 5 * 60 * 1000, // 5 minutes
    select: (data) => processTagsClientSide(data, queryParams),
  });
}
