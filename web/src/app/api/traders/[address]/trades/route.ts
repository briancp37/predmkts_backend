/**
 * Trader Trades API Route
 *
 * PRD #9 - Create REST API endpoints for traders
 *
 * Handles GET requests to /api/traders/[address]/trades with:
 * - Lookup by wallet address (normalized to lowercase)
 * - Pagination via limit and offset query params
 *
 * Returns:
 * - 200: Trades array with market and outcome data, total count, limit, offset
 * - 400: Invalid query parameters
 * - 404: Trader not found
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

interface RouteParams {
  params: Promise<{ address: string }>;
}

// Maximum limit to prevent excessive queries
const MAX_LIMIT = 100;
const DEFAULT_LIMIT = 20;

/**
 * GET /api/traders/[address]/trades
 *
 * Fetch trades for a trader with pagination
 */
export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { address } = await params;
    const searchParams = request.nextUrl.searchParams;

    if (!address) {
      return NextResponse.json({ error: 'Trader address is required' }, { status: 400 });
    }

    // Normalize address to lowercase for consistent lookup
    const normalizedAddress = address.toLowerCase();

    // Parse and validate limit
    const limitParam = searchParams.get('limit');
    let limit = DEFAULT_LIMIT;
    if (limitParam) {
      const parsedLimit = parseInt(limitParam, 10);
      if (isNaN(parsedLimit) || parsedLimit < 1) {
        return NextResponse.json({ error: 'Invalid limit parameter' }, { status: 400 });
      }
      limit = Math.min(parsedLimit, MAX_LIMIT);
    }

    // Parse and validate offset
    const offsetParam = searchParams.get('offset');
    let offset = 0;
    if (offsetParam) {
      const parsedOffset = parseInt(offsetParam, 10);
      if (isNaN(parsedOffset) || parsedOffset < 0) {
        return NextResponse.json({ error: 'Invalid offset parameter' }, { status: 400 });
      }
      offset = parsedOffset;
    }

    // First, find the trader to get their ID
    const trader = await prisma.trader.findUnique({
      where: { address: normalizedAddress },
      select: { id: true },
    });

    if (!trader) {
      return NextResponse.json({ error: 'Trader not found' }, { status: 404 });
    }

    // Execute queries in parallel
    const [trades, total] = await Promise.all([
      prisma.trade.findMany({
        where: { traderId: trader.id },
        include: {
          market: {
            select: {
              id: true,
              polymarketId: true,
              slug: true,
              question: true,
              category: true,
              resolved: true,
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
        skip: offset,
      }),
      prisma.trade.count({ where: { traderId: trader.id } }),
    ]);

    return NextResponse.json({
      trades,
      total,
      limit,
      offset,
    });
  } catch (error) {
    console.error(
      '[traders/[address]/trades] GET failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to fetch trader trades',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
