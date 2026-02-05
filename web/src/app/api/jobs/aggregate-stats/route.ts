/**
 * Market Stats Aggregation Job API Route
 *
 * PRD #7 - Create API route to trigger market stats aggregation
 *
 * Handles POST requests to /api/jobs/aggregate-stats with:
 * - CRON_SECRET authorization via Authorization header
 * - Optional body: { hour?: string } in ISO format
 *
 * Returns:
 * - 200: Aggregation completed successfully
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error with stack trace in development
 */

import { NextRequest, NextResponse } from 'next/server';
import { aggregateMarketStats } from '@/lib/jobs/aggregate-market-stats';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[aggregate-stats-api] CRON_SECRET not configured');
    return false;
  }

  // Support both "Bearer <token>" and direct token
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;

  return token === cronSecret;
}

/**
 * Request body interface
 */
interface RequestBody {
  hour?: string;
}

/**
 * POST /api/jobs/aggregate-stats
 *
 * Triggers market stats aggregation for a specific hour or the previous hour
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const startTime = Date.now();

  try {
    // Parse request body (may be empty)
    let body: RequestBody = {};
    try {
      body = await request.json();
    } catch {
      // Empty body is valid - will use default (previous hour)
    }

    // Parse hour if provided
    let targetHour: Date | undefined;
    if (body.hour) {
      targetHour = new Date(body.hour);
      if (isNaN(targetHour.getTime())) {
        return NextResponse.json(
          { error: 'Invalid hour format. Use ISO 8601 format (e.g., 2024-01-15T10:00:00Z)' },
          { status: 400 }
        );
      }
    }

    // Run aggregation
    const result = await aggregateMarketStats(targetHour);

    const totalExecutionTime = Date.now() - startTime;

    return NextResponse.json({
      success: result.success,
      marketsAggregated: result.marketsAggregated,
      hour: result.hour,
      executionTime: totalExecutionTime,
    });
  } catch (error) {
    console.error('[aggregate-stats-api] Error:', error instanceof Error ? error.message : error);

    const isDev = process.env.NODE_ENV === 'development';

    return NextResponse.json(
      {
        error: 'Aggregation failed',
        details: error instanceof Error ? error.message : 'Unknown error',
        ...(isDev && error instanceof Error && { stack: error.stack }),
      },
      { status: 500 }
    );
  }
}
