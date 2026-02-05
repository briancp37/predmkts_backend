/**
 * Snapshot Markets Job API Route
 *
 * PRD #7 - Create weekly full snapshot job
 *
 * Handles POST requests to /api/jobs/snapshot-markets with:
 * - CRON_SECRET authorization via Authorization header
 *
 * Returns:
 * - 200: Snapshot completed successfully with metrics
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { snapshotMarkets } from '@/lib/jobs/snapshot-markets';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[snapshot-markets] CRON_SECRET not configured');
    return false;
  }

  // Support both "Bearer <token>" and direct token
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;

  return token === cronSecret;
}

/**
 * POST /api/jobs/snapshot-markets
 *
 * Creates a full snapshot of all markets from Polymarket API and saves to S3
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    // Run the snapshot job
    const result = await snapshotMarkets();

    return NextResponse.json({
      success: true,
      count: result.count,
      key: result.key,
      duration_ms: result.duration_ms,
    });
  } catch (error) {
    console.error('[snapshot-markets] Job failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Snapshot failed',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
