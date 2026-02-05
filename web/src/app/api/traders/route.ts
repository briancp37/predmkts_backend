/**
 * Traders API Route
 *
 * PRD #14 - Create or update Traders API for explorer
 *
 * Handles GET requests to /api/traders with:
 * - Query params: search, sortBy (smartScore|totalPnl|totalTrades), limit, offset
 * - Case-insensitive search by address
 * - Descending sort order
 *
 * Returns:
 * - 200: { traders, total } with paginated results
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { Prisma } from '@prisma/client';

// Valid sort fields
const VALID_SORT_FIELDS = ['smartScore', 'totalPnl', 'totalTrades'] as const;
type SortField = (typeof VALID_SORT_FIELDS)[number];

/**
 * GET /api/traders
 *
 * Fetch traders with search, sorting, and pagination for the Trader Explorer page
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse query params
    const search = searchParams.get('search')?.trim() || '';
    const sortByParam = searchParams.get('sortBy') || 'smartScore';
    const limit = Math.min(parseInt(searchParams.get('limit') ?? '50', 10), 100);
    const offset = parseInt(searchParams.get('offset') ?? '0', 10);

    // Validate sortBy parameter
    const sortBy: SortField = VALID_SORT_FIELDS.includes(sortByParam as SortField)
      ? (sortByParam as SortField)
      : 'smartScore';

    // Validate limit and offset
    const validLimit = isNaN(limit) || limit < 1 ? 50 : limit;
    const validOffset = isNaN(offset) || offset < 0 ? 0 : offset;

    // Build where clause
    const where: Prisma.TraderWhereInput = {};

    // Add case-insensitive search filter if search term provided
    if (search) {
      where.address = {
        contains: search.toLowerCase(),
        mode: 'insensitive',
      };
    }

    // Build orderBy clause
    const orderBy: Prisma.TraderOrderByWithRelationInput = {
      [sortBy]: 'desc',
    };

    // Query traders with filters
    const [traders, total] = await Promise.all([
      prisma.trader.findMany({
        where,
        select: {
          id: true,
          address: true,
          username: true,
          smartScore: true,
          totalPnl: true,
          realizedPnl: true,
          totalTrades: true,
          winCount: true,
          lossCount: true,
          firstSeen: true,
        },
        orderBy,
        take: validLimit,
        skip: validOffset,
      }),
      prisma.trader.count({ where }),
    ]);

    // Transform response to include calculated fields
    const tradersWithStats = traders.map((trader) => ({
      ...trader,
      winRate:
        trader.winCount + trader.lossCount > 0
          ? trader.winCount / (trader.winCount + trader.lossCount)
          : 0,
    }));

    return NextResponse.json({
      traders: tradersWithStats,
      total,
      pagination: {
        limit: validLimit,
        offset: validOffset,
        hasMore: validOffset + traders.length < total,
      },
    });
  } catch (error) {
    console.error('[traders] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch traders',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
