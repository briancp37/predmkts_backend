/**
 * Sync Markets Job API Route
 *
 * PRD #6 - Create API routes for sync jobs
 *
 * Handles POST requests to /api/jobs/sync-markets with:
 * - CRON_SECRET authorization via Authorization header
 *
 * Returns:
 * - 200: Sync completed successfully with metrics
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { syncMarkets } from '@/lib/jobs/sync-markets';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[sync-markets] CRON_SECRET not configured');
    return false;
  }

  // Support both "Bearer <token>" and direct token
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;

  return token === cronSecret;
}

/**
 * POST /api/jobs/sync-markets
 *
 * Syncs all markets from Polymarket API to PostgreSQL
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    // Run the sync job
    const result = await syncMarkets();

    return NextResponse.json({
      success: true,
      fetched: result.fetched,
      savedToS3: result.savedToS3,
      upserted: result.upserted,
      s3Key: result.s3Key,
      isIncremental: result.isIncremental,
      lastSyncAt: result.lastSyncAt.toISOString(),
      duration_ms: result.duration_ms,
      // Keep 'count' for backwards compatibility
      count: result.upserted,
    });
  } catch (error) {
    console.error('[sync-markets] Job failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      { error: 'Sync failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
