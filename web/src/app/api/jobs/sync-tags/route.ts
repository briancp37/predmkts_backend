/**
 * Sync Tags Job API Route
 *
 * PRD #16 - Create API route for tag sync job
 *
 * Handles POST requests to /api/jobs/sync-tags with:
 * - CRON_SECRET authorization via Authorization header
 *
 * Returns:
 * - 200: Sync completed successfully with metrics
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { syncTags } from '@/lib/jobs/sync-tags';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[sync-tags] CRON_SECRET not configured');
    return false;
  }

  // Support both "Bearer <token>" and direct token
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;

  return token === cronSecret;
}

/**
 * POST /api/jobs/sync-tags
 *
 * Syncs tags by scanning market questions and categories
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    // Run the sync job
    const result = await syncTags();

    return NextResponse.json({
      success: true,
      tagsCreated: result.tagsCreated,
      tagsUpdated: result.tagsUpdated,
      marketsProcessed: result.marketsProcessed,
      marketTagsCreated: result.marketTagsCreated,
      duration_ms: result.duration_ms,
    });
  } catch (error) {
    console.error('[sync-tags] Job failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      { error: 'Sync failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
