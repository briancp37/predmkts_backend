/**
 * Market Trades API Route
 *
 * PRD #8 (Sprint 3) - Create trades API endpoint for markets
 *
 * Handles GET requests to /api/markets/[id]/trades with:
 * - limit query param (default: 50, max: 100)
 * - Trades ordered by timestamp descending
 *
 * Returns:
 * - 200: { trades } with trader and outcome data
 * - 400: Invalid parameters
 * - 404: Market not found
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * GET /api/markets/[id]/trades
 *
 * Fetch trades for a market, ordered by timestamp descending
 */
export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;
    const { searchParams } = new URL(request.url);

    // Parse and validate limit parameter
    const limitParam = searchParams.get('limit');
    let limit = 50;

    if (limitParam !== null) {
      const parsedLimit = parseInt(limitParam, 10);
      if (isNaN(parsedLimit) || parsedLimit < 1) {
        return NextResponse.json({ error: 'Invalid limit parameter' }, { status: 400 });
      }
      limit = Math.min(parsedLimit, 100); // Cap at 100
    }

    if (!id) {
      return NextResponse.json({ error: 'Market ID is required' }, { status: 400 });
    }

    // First, find the market by internal id, polymarketId, or slug
    const market = await prisma.market.findFirst({
      where: {
        OR: [{ id }, { polymarketId: id }, { slug: id }],
      },
      select: { id: true },
    });

    if (!market) {
      return NextResponse.json({ error: 'Market not found' }, { status: 404 });
    }

    // Query trades for this market
    const trades = await prisma.trade.findMany({
      where: {
        marketId: market.id,
      },
      include: {
        trader: {
          select: {
            id: true,
            address: true,
            username: true,
            smartScore: true,
          },
        },
        outcome: {
          select: {
            id: true,
            tokenId: true,
            outcomeName: true,
            currentPrice: true,
          },
        },
      },
      orderBy: {
        timestamp: 'desc',
      },
      take: limit,
    });

    return NextResponse.json({ trades });
  } catch (error) {
    console.error(
      '[markets/[id]/trades] GET failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to fetch trades',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
