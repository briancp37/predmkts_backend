/**
 * Smart Scores API Route
 *
 * PRD #7 - Create Smart Scores API endpoint for traders list
 *
 * Handles GET requests to /api/traders/smart-scores with:
 * - Query params: minScore, maxScore, limit, offset
 * - Filters traders with totalTrades >= 5
 * - Orders by smartScore descending
 *
 * Returns:
 * - 200: { traders, total } with paginated results
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

/**
 * GET /api/traders/smart-scores
 *
 * Fetch traders ranked by Smart Score with filtering and pagination
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse query params with defaults
    const minScore = parseFloat(searchParams.get('minScore') ?? '-100');
    const maxScore = parseFloat(searchParams.get('maxScore') ?? '100');
    const limit = Math.min(parseInt(searchParams.get('limit') ?? '50', 10), 100);
    const offset = parseInt(searchParams.get('offset') ?? '0', 10);

    // Validate score range
    const validMinScore = isNaN(minScore) ? -100 : Math.max(-100, Math.min(100, minScore));
    const validMaxScore = isNaN(maxScore) ? 100 : Math.max(-100, Math.min(100, maxScore));
    const validLimit = isNaN(limit) || limit < 1 ? 50 : limit;
    const validOffset = isNaN(offset) || offset < 0 ? 0 : offset;

    // Build where clause for filtering
    const where = {
      totalTrades: { gte: 5 },
      smartScore: {
        not: null,
        gte: validMinScore,
        lte: validMaxScore,
      },
    };

    // Query traders with smart scores
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
        orderBy: { smartScore: 'desc' },
        take: validLimit,
        skip: validOffset,
      }),
      prisma.trader.count({ where }),
    ]);

    // Transform response to include calculated fields
    const tradersWithStats = traders.map((trader, index) => ({
      ...trader,
      rank: validOffset + index + 1,
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
    console.error(
      '[traders/smart-scores] GET failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to fetch smart scores',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
