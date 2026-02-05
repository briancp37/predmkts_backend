/**
 * Single Market API Route
 *
 * PRD #8 - Create REST API endpoints for markets
 *
 * Handles GET requests to /api/markets/[id] with:
 * - Lookup by internal id, polymarketId, or slug
 *
 * Returns:
 * - 200: Market object with outcomes
 * - 404: Market not found
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * GET /api/markets/[id]
 *
 * Fetch a single market by id, polymarketId, or slug
 */
export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;

    if (!id) {
      return NextResponse.json({ error: 'Market ID is required' }, { status: 400 });
    }

    // Try to find market by internal id, polymarketId, or slug
    const market = await prisma.market.findFirst({
      where: {
        OR: [{ id }, { polymarketId: id }, { slug: id }],
      },
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
    });

    if (!market) {
      return NextResponse.json({ error: 'Market not found' }, { status: 404 });
    }

    return NextResponse.json(market);
  } catch (error) {
    console.error('[markets/[id]] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch market',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
