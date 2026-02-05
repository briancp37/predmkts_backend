/**
 * Single Event API Route
 *
 * Sprint 5 PRD #9 - Create events API endpoint
 *
 * Handles GET requests to /api/events/[id] with:
 * - Lookup by internal id or polymarketEventId
 *
 * Returns:
 * - 200: Event object with related markets and outcomes
 * - 404: Event not found
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * GET /api/events/[id]
 *
 * Fetch a single event by id or polymarketEventId
 * Includes related markets with their outcomes
 */
export async function GET(_request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;

    if (!id) {
      return NextResponse.json({ error: 'Event ID is required' }, { status: 400 });
    }

    // Try to find event by internal id or polymarketEventId
    const event = await prisma.event.findFirst({
      where: {
        OR: [{ id }, { polymarketEventId: id }],
      },
      include: {
        markets: {
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
          orderBy: {
            totalVolume: 'desc',
          },
        },
        _count: {
          select: { markets: true },
        },
      },
    });

    if (!event) {
      return NextResponse.json({ error: 'Event not found' }, { status: 404 });
    }

    return NextResponse.json(event);
  } catch (error) {
    console.error('[events/[id]] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch event',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
