/**
 * Tracked Trader by ID API Route
 *
 * PRD #9 - Create Tracked Trader update and delete endpoints
 *
 * Handles:
 * - GET /api/tracked-traders/[id] - Get a single tracked trader
 * - PATCH /api/tracked-traders/[id] - Update custom name
 * - DELETE /api/tracked-traders/[id] - Remove tracked trader
 *
 * Requires authentication via NextAuth session.
 * Verifies ownership before allowing modifications.
 */

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/app/api/auth/[...nextauth]/route';
import { prisma } from '@/lib/prisma';
import { z } from 'zod';

interface RouteParams {
  params: Promise<{ id: string }>;
}

// Validation schema for PATCH request body
const updateTrackedTraderSchema = z.object({
  customName: z.string().max(50, 'Custom name must be 50 characters or less').nullable().optional(),
});

/**
 * GET /api/tracked-traders/[id]
 *
 * Get a single tracked trader by ID.
 * Only returns if the user owns this tracked trader record.
 */
export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;

    // Verify user session
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;

    // Query the tracked trader
    const trackedTrader = await prisma.trackedTrader.findUnique({
      where: { id },
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

    if (!trackedTrader) {
      return NextResponse.json({ error: 'Tracked trader not found' }, { status: 404 });
    }

    // Verify ownership
    if (trackedTrader.userId !== userId) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

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

    return NextResponse.json(response);
  } catch (error) {
    console.error(
      '[tracked-traders/[id]] GET failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to fetch tracked trader',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

/**
 * PATCH /api/tracked-traders/[id]
 *
 * Update a tracked trader's custom name.
 * Only the owner can modify their tracked trader records.
 *
 * Request body:
 * - customName: string | null (optional, max 50 chars)
 */
export async function PATCH(request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;

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

    const validationResult = updateTrackedTraderSchema.safeParse(body);
    if (!validationResult.success) {
      const errorMessage = validationResult.error.issues[0]?.message || 'Validation error';
      return NextResponse.json({ error: errorMessage }, { status: 400 });
    }

    const { customName } = validationResult.data;

    // Query existing tracked trader
    const existingTracked = await prisma.trackedTrader.findUnique({
      where: { id },
    });

    if (!existingTracked) {
      return NextResponse.json({ error: 'Tracked trader not found' }, { status: 404 });
    }

    // Verify ownership
    if (existingTracked.userId !== userId) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    // Update the tracked trader
    const updatedTracked = await prisma.trackedTrader.update({
      where: { id },
      data: {
        customName: customName === undefined ? existingTracked.customName : customName,
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
      id: updatedTracked.id,
      customName: updatedTracked.customName,
      createdAt: updatedTracked.createdAt,
      trader: {
        ...updatedTracked.trader,
        winRate:
          updatedTracked.trader.winCount + updatedTracked.trader.lossCount > 0
            ? updatedTracked.trader.winCount /
              (updatedTracked.trader.winCount + updatedTracked.trader.lossCount)
            : 0,
      },
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error(
      '[tracked-traders/[id]] PATCH failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to update tracked trader',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/tracked-traders/[id]
 *
 * Remove a tracked trader from the user's watchlist.
 * Only the owner can delete their tracked trader records.
 */
export async function DELETE(_request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;

    // Verify user session
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;

    // Query existing tracked trader
    const existingTracked = await prisma.trackedTrader.findUnique({
      where: { id },
    });

    if (!existingTracked) {
      return NextResponse.json({ error: 'Tracked trader not found' }, { status: 404 });
    }

    // Verify ownership
    if (existingTracked.userId !== userId) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
    }

    // Delete the tracked trader
    await prisma.trackedTrader.delete({
      where: { id },
    });

    // Return 204 No Content
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    console.error(
      '[tracked-traders/[id]] DELETE failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to delete tracked trader',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
