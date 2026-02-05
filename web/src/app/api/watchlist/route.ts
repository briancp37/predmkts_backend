/**
 * Watchlist API Route
 *
 * Sprint 9 PRD #3 - Create Watchlist API endpoints for authenticated users
 *
 * Handles:
 * - GET /api/watchlist - Fetch user's watchlisted market IDs
 * - POST /api/watchlist - Add a market to watchlist
 *
 * Requires authentication via NextAuth session.
 */

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/app/api/auth/[...nextauth]/route';
import { prisma } from '@/lib/prisma';
import { z } from 'zod';

// Validation schema for POST request body
const addToWatchlistSchema = z.object({
  marketId: z.string().min(1, 'Market ID is required'),
});

/**
 * GET /api/watchlist
 *
 * Fetch all watchlisted market IDs for the authenticated user.
 * Returns an array of market IDs that the user has watchlisted.
 */
export async function GET() {
  try {
    // Verify user session
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;

    // Query user's watchlist
    const watchlist = await prisma.watchlist.findMany({
      where: { userId },
      select: {
        id: true,
        marketId: true,
        createdAt: true,
        market: {
          select: {
            polymarketId: true,
            question: true,
            slug: true,
          },
        },
      },
      orderBy: { createdAt: 'desc' },
    });

    // Transform response to return market IDs and basic info
    const watchlistItems = watchlist.map((item) => ({
      id: item.id,
      marketId: item.marketId,
      polymarketId: item.market.polymarketId,
      question: item.market.question,
      slug: item.market.slug,
      createdAt: item.createdAt,
    }));

    return NextResponse.json({
      watchlist: watchlistItems,
      marketIds: watchlist.map((item) => item.marketId),
    });
  } catch (error) {
    console.error('[watchlist] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch watchlist',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

/**
 * POST /api/watchlist
 *
 * Add a market to the authenticated user's watchlist.
 * Prevents duplicates via unique constraint.
 *
 * Request body:
 * - marketId: string (required, internal market ID from our database)
 */
export async function POST(request: NextRequest) {
  try {
    // Verify user session
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;

    // Parse and validate request body
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return NextResponse.json({ error: 'Invalid JSON in request body' }, { status: 400 });
    }

    const validationResult = addToWatchlistSchema.safeParse(body);
    if (!validationResult.success) {
      const errorMessage = validationResult.error.issues[0]?.message || 'Validation error';
      return NextResponse.json({ error: errorMessage }, { status: 400 });
    }

    const { marketId } = validationResult.data;

    // Verify the market exists
    const market = await prisma.market.findUnique({
      where: { id: marketId },
      select: { id: true, polymarketId: true, question: true, slug: true },
    });

    if (!market) {
      return NextResponse.json({ error: 'Market not found' }, { status: 404 });
    }

    // Check if already in watchlist
    const existingEntry = await prisma.watchlist.findUnique({
      where: {
        userId_marketId: {
          userId,
          marketId,
        },
      },
    });

    if (existingEntry) {
      return NextResponse.json({ error: 'Market is already in your watchlist' }, { status: 400 });
    }

    // Add to watchlist
    const watchlistEntry = await prisma.watchlist.create({
      data: {
        userId,
        marketId,
      },
      select: {
        id: true,
        marketId: true,
        createdAt: true,
        market: {
          select: {
            polymarketId: true,
            question: true,
            slug: true,
          },
        },
      },
    });

    return NextResponse.json(
      {
        id: watchlistEntry.id,
        marketId: watchlistEntry.marketId,
        polymarketId: watchlistEntry.market.polymarketId,
        question: watchlistEntry.market.question,
        slug: watchlistEntry.market.slug,
        createdAt: watchlistEntry.createdAt,
      },
      { status: 201 }
    );
  } catch (error) {
    console.error('[watchlist] POST failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to add to watchlist',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
