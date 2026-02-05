/**
 * Market Price History API Route
 *
 * PRD #6 - Create price history API endpoint for markets
 *
 * Handles GET requests to /api/markets/[id]/price-history with:
 * - Market lookup by id, polymarketId, or slug
 * - Optional hours query param (default: 72)
 *
 * Returns:
 * - 200: Array of { time, value } objects
 * - 404: Market not found
 * - 500: Internal server error (returns empty array with logging)
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { polymarketApi } from '@/lib/polymarket';

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * GET /api/markets/[id]/price-history
 *
 * Fetch price history for a market's first outcome token
 *
 * Query params:
 * - hours: Number of hours of history to fetch (default: 72)
 */
export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;

    if (!id) {
      return NextResponse.json({ error: 'Market ID is required' }, { status: 400 });
    }

    // Parse query parameters
    const searchParams = request.nextUrl.searchParams;
    const hours = parseInt(searchParams.get('hours') || '72', 10);

    // Validate hours parameter
    if (isNaN(hours) || hours < 1 || hours > 8760) {
      // Max 1 year
      return NextResponse.json({ error: 'Hours must be between 1 and 8760' }, { status: 400 });
    }

    // Lookup market from PostgreSQL by id, polymarketId, or slug
    const market = await prisma.market.findFirst({
      where: {
        OR: [{ id }, { polymarketId: id }, { slug: id }],
      },
      include: {
        outcomes: {
          select: {
            tokenId: true,
          },
          take: 1, // Get first outcome's tokenId
        },
      },
    });

    if (!market) {
      return NextResponse.json({ error: 'Market not found' }, { status: 404 });
    }

    // Get first outcome's tokenId for price history query
    const tokenId = market.outcomes[0]?.tokenId;

    if (!tokenId) {
      // Market has no outcomes, return empty array
      return NextResponse.json([]);
    }

    // Calculate time range
    const endTs = Math.floor(Date.now() / 1000);
    const startTs = endTs - hours * 60 * 60;

    try {
      // Call Polymarket CLOB API for price history
      const priceHistory = await polymarketApi.getPriceHistory(tokenId, {
        startTs,
        endTs,
      });

      // Transform response to array of { time, value } objects
      const formattedHistory = priceHistory.map((point) => ({
        time: point.t,
        value: point.p,
      }));

      return NextResponse.json(formattedHistory);
    } catch (apiError) {
      // Log error but return empty array (graceful degradation)
      console.error(
        '[markets/[id]/price-history] Polymarket API failed:',
        apiError instanceof Error ? apiError.message : apiError
      );
      return NextResponse.json([]);
    }
  } catch (error) {
    console.error(
      '[markets/[id]/price-history] GET failed:',
      error instanceof Error ? error.message : error
    );

    // Return empty array on error (graceful degradation per PRD)
    return NextResponse.json([]);
  }
}
