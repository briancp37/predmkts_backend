/**
 * Smart Score Computation Job API Route
 *
 * PRD #11 - Create API route to trigger smart score computation
 *
 * Handles POST requests to /api/jobs/compute-smart-scores with:
 * - CRON_SECRET authorization via Authorization header
 * - Optional body: { date?: string } in ISO format
 *
 * Returns:
 * - 200: Computation completed successfully
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 400: Bad request (invalid date format)
 * - 500: Internal server error with stack trace in development
 */

import { NextRequest, NextResponse } from 'next/server';
import { computeSmartScores } from '@/lib/jobs/compute-smart-scores';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[compute-smart-scores-api] CRON_SECRET not configured');
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
  date?: string;
}

/**
 * POST /api/jobs/compute-smart-scores
 *
 * Triggers smart score computation for all traders
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    // Parse request body (may be empty)
    let body: RequestBody = {};
    try {
      body = await request.json();
    } catch {
      // Empty body is valid - will use current date
    }

    // Parse optional date parameter
    let targetDate: Date | undefined;
    if (body.date) {
      const parsedDate = new Date(body.date);
      if (isNaN(parsedDate.getTime())) {
        return NextResponse.json(
          {
            error: 'Invalid date format. Please provide a valid ISO date string.',
            provided: body.date,
          },
          { status: 400 }
        );
      }
      targetDate = parsedDate;
    }

    // Run smart score computation
    const result = await computeSmartScores(targetDate);

    return NextResponse.json({
      success: result.success,
      tradersScored: result.tradersScored,
      executionTime: result.executionTime,
    });
  } catch (error) {
    console.error(
      '[compute-smart-scores-api] Error:',
      error instanceof Error ? error.message : error
    );

    const isDev = process.env.NODE_ENV === 'development';

    return NextResponse.json(
      {
        error: 'Smart score computation failed',
        details: error instanceof Error ? error.message : 'Unknown error',
        ...(isDev && error instanceof Error && { stack: error.stack }),
      },
      { status: 500 }
    );
  }
}
