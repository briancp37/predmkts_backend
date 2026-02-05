/**
 * Watchlist Market API Route
 *
 * Sprint 9 PRD #3 - Delete endpoint for removing markets from watchlist
 *
 * Handles:
 * - DELETE /api/watchlist/[marketId] - Remove a market from watchlist
 *
 * Requires authentication via NextAuth session.
 */

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/app/api/auth/[...nextauth]/route';
import { prisma } from '@/lib/prisma';

interface RouteParams {
  params: Promise<{
    marketId: string;
  }>;
}

/**
 * DELETE /api/watchlist/[marketId]
 *
 * Remove a market from the authenticated user's watchlist.
 */
export async function DELETE(_request: NextRequest, { params }: RouteParams) {
  try {
    // Verify user session
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;
    const { marketId } = await params;

    if (!marketId) {
      return NextResponse.json({ error: 'Market ID is required' }, { status: 400 });
    }

    // Find the watchlist entry
    const watchlistEntry = await prisma.watchlist.findUnique({
      where: {
        userId_marketId: {
          userId,
          marketId,
        },
      },
    });

    if (!watchlistEntry) {
      return NextResponse.json({ error: 'Market not found in your watchlist' }, { status: 404 });
    }

    // Delete the watchlist entry
    await prisma.watchlist.delete({
      where: {
        id: watchlistEntry.id,
      },
    });

    return NextResponse.json({ success: true, marketId });
  } catch (error) {
    console.error('[watchlist] DELETE failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to remove from watchlist',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
