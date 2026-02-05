/**
 * Calculate Smart Scores Job API Route
 *
 * PRD #6 - Smart Score calculation job API
 *
 * Handles POST requests to /api/jobs/calculate-scores with:
 * - CRON_SECRET authorization via Authorization header
 *
 * Returns:
 * - 200: Calculation completed successfully with count of updated traders
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { calculateAllSmartScores } from '@/lib/smart-scores/calculator';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[calculate-scores] CRON_SECRET not configured');
    return false;
  }

  // Support both "Bearer <token>" and direct token formats
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;

  return token === cronSecret;
}

/**
 * POST /api/jobs/calculate-scores
 *
 * Calculates Smart Scores for all eligible traders.
 * Updates PostgreSQL traders table and creates ClickHouse snapshots.
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const startTime = Date.now();

    // Run the score calculation job
    const count = await calculateAllSmartScores();

    const duration = Date.now() - startTime;

    return NextResponse.json({
      success: true,
      updated: count,
      duration_ms: duration,
    });
  } catch (error) {
    console.error('[calculate-scores] Job failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Score calculation failed',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
