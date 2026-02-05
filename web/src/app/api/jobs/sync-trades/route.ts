/**
 * Sync Trades Job API Route
 *
 * PRD #6 - Create API routes for sync jobs
 * PRD #2 - Add --initial flag to sync-trades job for 72h backfill from S3
 *
 * Handles POST requests to /api/jobs/sync-trades with:
 * - CRON_SECRET authorization via Authorization header
 * - Optional sinceMinutes query parameter (default: 5)
 * - Optional initial query parameter for 72h backfill from S3
 *
 * Returns:
 * - 200: Sync completed successfully with count of synced trades
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { syncRecentTrades, initialBackfill } from '@/lib/jobs/sync-trades';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[sync-trades] CRON_SECRET not configured');
    return false;
  }

  // Support both "Bearer <token>" and direct token
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;

  return token === cronSecret;
}

/**
 * POST /api/jobs/sync-trades
 *
 * Syncs recent trades from Polymarket API to ClickHouse.
 *
 * Query Parameters:
 * - sinceMinutes: Number of minutes to look back for recent trades (default: 5)
 * - initial: If 'true', performs a 72h backfill from S3 instead of normal sync
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const startTime = Date.now();

    const { searchParams } = new URL(request.url);
    const isInitial = searchParams.get('initial') === 'true';

    // Check if this is an initial 72h backfill request
    if (isInitial) {
      console.log('[sync-trades] Running initial 72h backfill from S3...');

      const result = await initialBackfill();

      const duration = Date.now() - startTime;

      return NextResponse.json({
        success: true,
        mode: 'initial',
        tradesInserted: result.tradesInserted,
        startTime: result.startTime.toISOString(),
        endTime: result.endTime.toISOString(),
        duration_ms: duration,
      });
    }

    // Normal sync: Get optional sinceMinutes from query params (default: 5)
    const sinceMinutes = parseInt(searchParams.get('sinceMinutes') || '5', 10);

    // Run the normal sync job
    const count = await syncRecentTrades(sinceMinutes);

    const duration = Date.now() - startTime;

    return NextResponse.json({
      success: true,
      mode: 'incremental',
      count,
      sinceMinutes,
      duration_ms: duration,
    });
  } catch (error) {
    console.error('[sync-trades] Job failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      { error: 'Sync failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
