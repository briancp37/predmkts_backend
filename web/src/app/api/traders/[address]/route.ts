/**
 * Single Trader API Route
 *
 * PRD #9 - Create REST API endpoints for traders
 *
 * Handles GET requests to /api/traders/[address] with:
 * - Lookup by wallet address (normalized to lowercase)
 *
 * Returns:
 * - 200: Trader object with positions (quantity > 0) and market/outcome data
 * - 404: Trader not found
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

interface RouteParams {
  params: Promise<{ address: string }>;
}

/**
 * GET /api/traders/[address]
 *
 * Fetch a single trader by wallet address
 */
export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const { address } = await params;

    if (!address) {
      return NextResponse.json({ error: 'Trader address is required' }, { status: 400 });
    }

    // Normalize address to lowercase for consistent lookup
    const normalizedAddress = address.toLowerCase();

    // Find trader by address
    const trader = await prisma.trader.findUnique({
      where: { address: normalizedAddress },
      include: {
        positions: {
          where: {
            quantity: { gt: 0 },
          },
          include: {
            market: {
              select: {
                id: true,
                polymarketId: true,
                slug: true,
                question: true,
                category: true,
                resolved: true,
                outcome: true,
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
        },
        _count: {
          select: {
            trades: true,
          },
        },
      },
    });

    if (!trader) {
      return NextResponse.json({ error: 'Trader not found' }, { status: 404 });
    }

    // Transform response to include tradeCount at top level
    const response = {
      id: trader.id,
      address: trader.address,
      username: trader.username,
      firstSeen: trader.firstSeen,
      smartScore: trader.smartScore,
      totalPnl: trader.totalPnl,
      realizedPnl: trader.realizedPnl,
      totalTrades: trader.totalTrades,
      winCount: trader.winCount,
      lossCount: trader.lossCount,
      createdAt: trader.createdAt,
      updatedAt: trader.updatedAt,
      positions: trader.positions,
      tradeCount: trader._count.trades,
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error(
      '[traders/[address]] GET failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to fetch trader',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
