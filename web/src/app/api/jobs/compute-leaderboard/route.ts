/**
 * Leaderboard Computation Job API Route
 *
 * PRD #9 - Create API route to trigger leaderboard computation
 *
 * Handles POST requests to /api/jobs/compute-leaderboard with:
 * - CRON_SECRET authorization via Authorization header
 * - Optional body: { periods?: string[] } - array of periods to compute
 *
 * Returns:
 * - 200: Computation completed successfully
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error with stack trace in development
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  computeAllLeaderboards,
  LeaderboardPeriod,
  LeaderboardResult,
} from '@/lib/jobs/compute-leaderboard';

/**
 * Valid period values
 */
const VALID_PERIODS: LeaderboardPeriod[] = ['1d', '7d', '30d', 'all'];

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[compute-leaderboard-api] CRON_SECRET not configured');
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
  periods?: string[];
}

/**
 * Response interface for aggregated results
 */
interface ComputeLeaderboardResponse {
  success: boolean;
  periods: Array<{
    period: LeaderboardPeriod;
    tradersRanked: number;
    topTrader: { address: string; pnl: number } | null;
  }>;
  totalTradersRanked: number;
  executionTime: number;
}

/**
 * Validate period string is a valid LeaderboardPeriod
 */
function isValidPeriod(period: string): period is LeaderboardPeriod {
  return VALID_PERIODS.includes(period as LeaderboardPeriod);
}

/**
 * POST /api/jobs/compute-leaderboard
 *
 * Triggers leaderboard computation for specified periods or all periods by default
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
      // Empty body is valid - will use default (all periods)
    }

    // Validate and parse periods
    let periodsToCompute: LeaderboardPeriod[] = VALID_PERIODS;

    if (body.periods && Array.isArray(body.periods)) {
      // Filter to only valid periods
      const validPeriods = body.periods.filter(isValidPeriod);

      if (validPeriods.length === 0) {
        return NextResponse.json(
          {
            error: 'Invalid periods. Valid values are: 1d, 7d, 30d, all',
            provided: body.periods,
          },
          { status: 400 }
        );
      }

      periodsToCompute = validPeriods;
    }

    // Run computation for each period
    const results = await computeAllLeaderboards(periodsToCompute);

    // Aggregate results
    const totalTradersRanked = results.reduce((sum, r) => sum + r.tradersRanked, 0);
    const totalExecutionTime = Date.now() - startTime;

    const response: ComputeLeaderboardResponse = {
      success: true,
      periods: results.map((r: LeaderboardResult) => ({
        period: r.period,
        tradersRanked: r.tradersRanked,
        topTrader: r.topTrader,
      })),
      totalTradersRanked,
      executionTime: totalExecutionTime,
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error(
      '[compute-leaderboard-api] Error:',
      error instanceof Error ? error.message : error
    );

    const isDev = process.env.NODE_ENV === 'development';

    return NextResponse.json(
      {
        error: 'Leaderboard computation failed',
        details: error instanceof Error ? error.message : 'Unknown error',
        ...(isDev && error instanceof Error && { stack: error.stack }),
      },
      { status: 500 }
    );
  }
}
