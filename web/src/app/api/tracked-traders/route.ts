/**
 * Tracked Traders API Route
 *
 * PRD #8 - Create Tracked Traders CRUD API endpoints
 *
 * Handles:
 * - GET /api/tracked-traders - Fetch user's tracked traders
 * - POST /api/tracked-traders - Add a new tracked trader
 *
 * Requires authentication via NextAuth session.
 * Enforces tier limits: FREE = 6 max, PRO = 50 max
 */

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/app/api/auth/[...nextauth]/route';
import { prisma } from '@/lib/prisma';
import { z } from 'zod';

// Tier limits for tracked traders
const TIER_LIMITS = {
  FREE: 6,
  PRO: 50,
} as const;

// Validation schema for POST request body
const addTrackedTraderSchema = z.object({
  traderAddress: z
    .string()
    .min(1, 'Trader address is required')
    .regex(/^0x[a-fA-F0-9]{40}$/, 'Invalid Ethereum address format'),
  customName: z.string().max(50, 'Custom name must be 50 characters or less').optional(),
});

/**
 * GET /api/tracked-traders
 *
 * Fetch all tracked traders for the authenticated user.
 * Returns trader details including address, username, smartScore, totalPnl, totalTrades.
 */
export async function GET() {
  try {
    // Verify user session
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;

    // Query user's tracked traders with trader details
    const trackedTraders = await prisma.trackedTrader.findMany({
      where: { userId },
      include: {
        trader: {
          select: {
            id: true,
            address: true,
            username: true,
            smartScore: true,
            totalPnl: true,
            totalTrades: true,
            winCount: true,
            lossCount: true,
          },
        },
      },
      orderBy: { createdAt: 'desc' },
    });

    // Transform response to include calculated fields
    const transformedTraders = trackedTraders.map((tt) => ({
      id: tt.id,
      customName: tt.customName,
      createdAt: tt.createdAt,
      trader: {
        ...tt.trader,
        winRate:
          tt.trader.winCount + tt.trader.lossCount > 0
            ? tt.trader.winCount / (tt.trader.winCount + tt.trader.lossCount)
            : 0,
      },
    }));

    return NextResponse.json({ trackedTraders: transformedTraders });
  } catch (error) {
    console.error('[tracked-traders] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch tracked traders',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

/**
 * POST /api/tracked-traders
 *
 * Add a new tracked trader for the authenticated user.
 * Validates tier limits and prevents duplicates.
 *
 * Request body:
 * - traderAddress: string (required, Ethereum address)
 * - customName: string (optional, max 50 chars)
 */
export async function POST(request: NextRequest) {
  try {
    // Verify user session
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;
    const tier = session.user.tier || 'FREE';

    // Parse and validate request body
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return NextResponse.json({ error: 'Invalid JSON in request body' }, { status: 400 });
    }

    const validationResult = addTrackedTraderSchema.safeParse(body);
    if (!validationResult.success) {
      const errorMessage = validationResult.error.issues[0]?.message || 'Validation error';
      return NextResponse.json({ error: errorMessage }, { status: 400 });
    }

    const { traderAddress, customName } = validationResult.data;

    // Normalize address to lowercase
    const normalizedAddress = traderAddress.toLowerCase();

    // Check tier limit
    const existingCount = await prisma.trackedTrader.count({
      where: { userId },
    });

    const limit = TIER_LIMITS[tier as keyof typeof TIER_LIMITS] || TIER_LIMITS.FREE;
    if (existingCount >= limit) {
      return NextResponse.json(
        {
          error: 'Tracked trader limit reached',
          details: `Your ${tier} tier allows tracking up to ${limit} traders. Upgrade to PRO for more.`,
          limit,
          current: existingCount,
        },
        { status: 403 }
      );
    }

    // Find or create the trader
    let trader = await prisma.trader.findUnique({
      where: { address: normalizedAddress },
    });

    if (!trader) {
      // Create new trader record
      trader = await prisma.trader.create({
        data: {
          address: normalizedAddress,
        },
      });
    }

    // Check for duplicate tracking
    const existingTracked = await prisma.trackedTrader.findUnique({
      where: {
        userId_traderId: {
          userId,
          traderId: trader.id,
        },
      },
    });

    if (existingTracked) {
      return NextResponse.json({ error: 'You are already tracking this trader' }, { status: 400 });
    }

    // Create tracked trader record
    const trackedTrader = await prisma.trackedTrader.create({
      data: {
        userId,
        traderId: trader.id,
        customName: customName || null,
      },
      include: {
        trader: {
          select: {
            id: true,
            address: true,
            username: true,
            smartScore: true,
            totalPnl: true,
            totalTrades: true,
            winCount: true,
            lossCount: true,
          },
        },
      },
    });

    // Transform response
    const response = {
      id: trackedTrader.id,
      customName: trackedTrader.customName,
      createdAt: trackedTrader.createdAt,
      trader: {
        ...trackedTrader.trader,
        winRate:
          trackedTrader.trader.winCount + trackedTrader.trader.lossCount > 0
            ? trackedTrader.trader.winCount /
              (trackedTrader.trader.winCount + trackedTrader.trader.lossCount)
            : 0,
      },
    };

    return NextResponse.json(response, { status: 201 });
  } catch (error) {
    console.error('[tracked-traders] POST failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to add tracked trader',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
