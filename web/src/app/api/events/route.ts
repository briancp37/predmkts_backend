/**
 * Events API Route
 *
 * Sprint 5 PRD #9 - Create events API endpoint
 *
 * Handles GET requests to /api/events with:
 * - search: Search by title text
 * - category: Filter by category
 * - limit: Number of results (default: 20, max: 100)
 * - offset: Pagination offset (default: 0)
 *
 * Returns:
 * - 200: Events array with market counts, total, limit, offset
 * - 400: Invalid query parameters
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { Prisma } from '@prisma/client';

// Maximum limit to prevent excessive queries
const MAX_LIMIT = 100;
const DEFAULT_LIMIT = 20;

/**
 * GET /api/events
 *
 * Fetch events with optional filtering and pagination
 * Orders by market count descending (most active events first)
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse query parameters
    const search = searchParams.get('search');
    const category = searchParams.get('category');
    const limitParam = searchParams.get('limit');
    const offsetParam = searchParams.get('offset');

    // Parse and validate limit
    let limit = DEFAULT_LIMIT;
    if (limitParam) {
      const parsedLimit = parseInt(limitParam, 10);
      if (isNaN(parsedLimit) || parsedLimit < 1) {
        return NextResponse.json({ error: 'Invalid limit parameter' }, { status: 400 });
      }
      limit = Math.min(parsedLimit, MAX_LIMIT);
    }

    // Parse and validate offset
    let offset = 0;
    if (offsetParam) {
      const parsedOffset = parseInt(offsetParam, 10);
      if (isNaN(parsedOffset) || parsedOffset < 0) {
        return NextResponse.json({ error: 'Invalid offset parameter' }, { status: 400 });
      }
      offset = parsedOffset;
    }

    // Build where clause
    const where: Prisma.EventWhereInput = {};

    if (search) {
      where.title = {
        contains: search,
        mode: 'insensitive',
      };
    }

    if (category) {
      where.category = category;
    }

    // Execute queries in parallel
    const [events, total] = await Promise.all([
      prisma.event.findMany({
        where,
        include: {
          _count: {
            select: { markets: true },
          },
        },
        orderBy: {
          markets: {
            _count: 'desc',
          },
        },
        take: limit,
        skip: offset,
      }),
      prisma.event.count({ where }),
    ]);

    return NextResponse.json({
      events,
      total,
      limit,
      offset,
    });
  } catch (error) {
    console.error('[events] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch events',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
