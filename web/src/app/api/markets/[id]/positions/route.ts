/**
 * Market Positions API Route
 *
 * PRD #7 (Sprint 3) - Create positions API endpoint for markets
 *
 * Handles GET requests to /api/markets/[id]/positions with:
 * - limit query param (default: 20, max: 100)
 * - Positions ordered by investedUsd descending
 *
 * Returns:
 * - 200: { positions } with trader and outcome data
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
 * GET /api/markets/[id]/positions
 *
 * Fetch positions for a market, ordered by invested amount
 */
export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;
    const { searchParams } = new URL(request.url);

    // Parse and validate limit parameter
    const limitParam = searchParams.get('limit');
    let limit = 20;

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

    // Query positions for this market where quantity > 0
    const positions = await prisma.position.findMany({
      where: {
        marketId: market.id,
        quantity: { gt: 0 },
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
        investedUsd: 'desc',
      },
      take: limit,
    });

    return NextResponse.json({ positions });
  } catch (error) {
    console.error(
      '[markets/[id]/positions] GET failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to fetch positions',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
