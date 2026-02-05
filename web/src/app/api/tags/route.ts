/**
 * Tags API Route
 *
 * Sprint 9 PRD #4 - Create Tags API endpoint to fetch all available market tags
 *
 * Handles:
 * - GET /api/tags - Fetch all available tags with market counts
 *
 * Query parameters:
 * - search: Filter tags by name (case-insensitive partial match)
 * - sort: Sort by 'popular' (market count, default) or 'alphabetical'
 * - limit: Maximum number of tags to return (default: 100)
 *
 * Returns:
 * - 200: { tags: Tag[], total: number }
 * - 400: Invalid query parameters
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

// Valid sort options
const VALID_SORT_OPTIONS = ['popular', 'alphabetical'] as const;
type SortOption = (typeof VALID_SORT_OPTIONS)[number];

// Limits
const DEFAULT_LIMIT = 100;
const MAX_LIMIT = 500;

/**
 * Tag response with market count
 */
interface TagResponse {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  marketCount: number;
  createdAt: string;
}

/**
 * GET /api/tags
 *
 * Fetch all available market tags with their associated market counts.
 * Supports filtering by name and sorting by popularity or alphabetically.
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse search parameter
    const search = searchParams.get('search')?.trim() || null;

    // Parse sort parameter
    const sortParam = searchParams.get('sort') ?? 'popular';
    if (!VALID_SORT_OPTIONS.includes(sortParam as SortOption)) {
      return NextResponse.json(
        { error: `Invalid sort parameter. Must be one of: ${VALID_SORT_OPTIONS.join(', ')}` },
        { status: 400 }
      );
    }
    const sort = sortParam as SortOption;

    // Parse limit parameter
    const limitParam = searchParams.get('limit');
    let limit = DEFAULT_LIMIT;
    if (limitParam) {
      const parsedLimit = parseInt(limitParam, 10);
      if (isNaN(parsedLimit) || parsedLimit < 1) {
        return NextResponse.json({ error: 'Invalid limit parameter' }, { status: 400 });
      }
      limit = Math.min(parsedLimit, MAX_LIMIT);
    }

    // Build where clause for search
    const where = search
      ? {
          name: {
            contains: search,
            mode: 'insensitive' as const,
          },
        }
      : {};

    // Query tags with market counts using aggregation
    // We use a raw query approach via Prisma's groupBy/count for efficiency
    const tags = await prisma.tag.findMany({
      where,
      select: {
        id: true,
        name: true,
        slug: true,
        description: true,
        createdAt: true,
        _count: {
          select: {
            markets: true,
          },
        },
      },
      take: limit,
      orderBy:
        sort === 'alphabetical'
          ? { name: 'asc' }
          : // For popular sort, we need to order by market count
            // Prisma doesn't support ordering by _count directly in findMany,
            // so we'll sort in memory after fetching
            { createdAt: 'desc' },
    });

    // Transform response
    let tagResponses: TagResponse[] = tags.map((tag) => ({
      id: tag.id,
      name: tag.name,
      slug: tag.slug,
      description: tag.description,
      marketCount: tag._count.markets,
      createdAt: tag.createdAt.toISOString(),
    }));

    // Sort by market count if popular sort requested
    if (sort === 'popular') {
      tagResponses.sort((a, b) => b.marketCount - a.marketCount);
    }

    // Get total count (for pagination info if needed later)
    const total = await prisma.tag.count({ where });

    return NextResponse.json({
      tags: tagResponses,
      total,
    });
  } catch (error) {
    console.error('[tags] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch tags',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
