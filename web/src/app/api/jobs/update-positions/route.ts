/**
 * Update Positions Job API Route
 *
 * PRD #6 - Create API routes for sync jobs
 *
 * Handles POST requests to /api/jobs/update-positions with:
 * - CRON_SECRET authorization via Authorization header
 *
 * Returns:
 * - 200: Update completed successfully with positions and traders updated counts
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { updatePositionValues } from '@/lib/jobs/update-positions';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[update-positions] CRON_SECRET not configured');
    return false;
  }

  // Support both "Bearer <token>" and direct token
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;

  return token === cronSecret;
}

/**
 * POST /api/jobs/update-positions
 *
 * Updates all position values with current market prices
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const startTime = Date.now();

    // Run the update job
    const result = await updatePositionValues();

    const duration = Date.now() - startTime;

    return NextResponse.json({
      success: true,
      positionsUpdated: result.positionsUpdated,
      tradersUpdated: result.tradersUpdated,
      duration_ms: duration,
    });
  } catch (error) {
    console.error('[update-positions] Job failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      { error: 'Update failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
