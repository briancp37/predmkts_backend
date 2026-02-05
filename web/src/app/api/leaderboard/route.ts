/**
 * Leaderboard API Route
 *
 * PRD #10 - Create Leaderboard API endpoint (ClickHouse)
 *
 * Handles GET requests to /api/leaderboard with:
 * - Query params: period (default '7d'), limit (default 100)
 * - Queries ClickHouse leaderboard_daily table
 * - Filters by period and calculated_date = today()
 * - Orders by rank
 *
 * Returns:
 * - 200: { leaderboard } with ranked traders
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { queryClickHouse } from '@/lib/clickhouse';

/**
 * Valid period options for the leaderboard
 */
type LeaderboardPeriod = '1d' | '7d' | '30d' | 'all';

/**
 * Leaderboard entry returned from ClickHouse
 */
interface LeaderboardEntry {
  trader_address: string;
  pnl: number;
  trade_count: number;
  win_rate: number;
  rank: number;
}

/**
 * Map period string to ClickHouse Enum8 value
 */
function getPeriodValue(period: string): number {
  switch (period) {
    case '1d':
      return 1;
    case '7d':
      return 7;
    case '30d':
      return 30;
    case 'all':
      return 0;
    default:
      return 7; // default to 7d
  }
}

/**
 * Validate and normalize period parameter
 */
function validatePeriod(period: string | null): LeaderboardPeriod {
  const validPeriods: LeaderboardPeriod[] = ['1d', '7d', '30d', 'all'];
  if (period && validPeriods.includes(period as LeaderboardPeriod)) {
    return period as LeaderboardPeriod;
  }
  return '7d'; // default
}

/**
 * GET /api/leaderboard
 *
 * Fetch PnL leaderboard from the leaderboard_daily table (ClickHouse)
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse query params with defaults
    const periodParam = searchParams.get('period');
    const limitParam = searchParams.get('limit');

    // Validate period
    const period = validatePeriod(periodParam);
    const periodValue = getPeriodValue(period);

    // Validate and clamp limit
    const parsedLimit = parseInt(limitParam ?? '100', 10);
    const validLimit = isNaN(parsedLimit) || parsedLimit < 1 ? 100 : Math.min(parsedLimit, 500);

    // Query ClickHouse leaderboard_daily table
    // Using Enum8 type for period parameter to match the table schema
    const query = `
      SELECT
        trader_address,
        pnl,
        trade_count,
        win_rate,
        rank
      FROM leaderboard_daily
      WHERE period = {periodValue:UInt8}
        AND calculated_date = today()
      ORDER BY rank
      LIMIT {limit:UInt32}
    `;

    const entries = await queryClickHouse<LeaderboardEntry>(query, {
      periodValue,
      limit: validLimit,
    });

    // Normalize numeric values that may come as strings from ClickHouse
    const normalizedLeaderboard = entries.map((entry) => ({
      ...entry,
      pnl: typeof entry.pnl === 'string' ? parseFloat(entry.pnl) : entry.pnl,
      trade_count:
        typeof entry.trade_count === 'string' ? parseInt(entry.trade_count, 10) : entry.trade_count,
      win_rate: typeof entry.win_rate === 'string' ? parseFloat(entry.win_rate) : entry.win_rate,
      rank: typeof entry.rank === 'string' ? parseInt(entry.rank, 10) : entry.rank,
    }));

    return NextResponse.json({
      leaderboard: normalizedLeaderboard,
      period,
    });
  } catch (error) {
    console.error('[leaderboard] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch leaderboard',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
