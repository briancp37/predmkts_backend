/**
 * Markets API Route
 *
 * PRD #8 - Create REST API endpoints for markets
 *
 * Handles GET requests to /api/markets with:
 * - search: Search by question text
 * - category: Filter by category
 * - resolved: Filter by resolved status (true/false)
 * - limit: Number of results (default: 20, max: 100)
 * - offset: Pagination offset (default: 0)
 *
 * Returns:
 * - 200: Markets array with total count, limit, offset
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
 * GET /api/markets
 *
 * Fetch markets with optional filtering and pagination
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse query parameters
    const search = searchParams.get('search');
    const category = searchParams.get('category');
    const resolvedParam = searchParams.get('resolved');
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

    // Parse resolved filter
    let resolved: boolean | undefined;
    if (resolvedParam !== null) {
      if (resolvedParam === 'true') {
        resolved = true;
      } else if (resolvedParam === 'false') {
        resolved = false;
      } else {
        return NextResponse.json(
          { error: 'Invalid resolved parameter (must be true or false)' },
          { status: 400 }
        );
      }
    }

    // Build where clause
    const where: Prisma.MarketWhereInput = {};

    if (search) {
      where.question = {
        contains: search,
        mode: 'insensitive',
      };
    }

    if (category) {
      where.category = category;
    }

    if (resolved !== undefined) {
      where.resolved = resolved;
    }

    // Execute queries in parallel
    const [markets, total] = await Promise.all([
      prisma.market.findMany({
        where,
        include: {
          outcomes: {
            select: {
              id: true,
              tokenId: true,
              outcomeName: true,
              currentPrice: true,
              volume: true,
            },
          },
        },
        orderBy: {
          totalVolume: 'desc',
        },
        take: limit,
        skip: offset,
      }),
      prisma.market.count({ where }),
    ]);

    return NextResponse.json({
      markets,
      total,
      limit,
      offset,
    });
  } catch (error) {
    console.error('[markets] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch markets',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
