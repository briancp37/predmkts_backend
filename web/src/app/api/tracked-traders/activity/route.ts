/**
 * Tracked Traders Activity Feed API Route
 *
 * PRD #10 - Create Tracked Traders activity feed API endpoint
 *
 * Handles GET requests to /api/tracked-traders/activity with:
 * - Query params: limit (default 100, max 500), minAmount (default 0)
 * - Queries ClickHouse trades_recent table for trades from tracked addresses
 * - Joins with PostgreSQL tracked traders for custom names
 *
 * Returns:
 * - 200: { trades, trackedCount } with filtered activity
 * - 401: Unauthorized
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/app/api/auth/[...nextauth]/route';
import { prisma } from '@/lib/prisma';
import { queryClickHouse } from '@/lib/clickhouse';

/**
 * Trade row returned from ClickHouse trades_recent table
 */
interface ActivityTrade {
  id: string;
  trader_address: string;
  market_id: string;
  outcome_name: string;
  market_question: string;
  side: 'BUY' | 'SELL';
  price: number;
  amount: number;
  usd_value: number;
  timestamp: string;
  smart_score: number | null;
}

/**
 * Transformed trade with custom name
 */
interface ActivityTradeWithName extends ActivityTrade {
  customName: string | null;
}

/**
 * GET /api/tracked-traders/activity
 *
 * Fetch recent trades from user's tracked traders (ClickHouse)
 */
export async function GET(request: NextRequest) {
  try {
    // Verify user session
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const userId = session.user.id;

    // Parse query params with defaults
    const searchParams = request.nextUrl.searchParams;
    const limit = parseInt(searchParams.get('limit') ?? '100', 10);
    const minAmount = parseFloat(searchParams.get('minAmount') ?? '0');

    // Validate parameters
    const validLimit = isNaN(limit) || limit < 1 ? 100 : Math.min(limit, 500);
    const validMinAmount = isNaN(minAmount) || minAmount < 0 ? 0 : minAmount;

    // Get user's tracked traders with their addresses
    const trackedTraders = await prisma.trackedTrader.findMany({
      where: { userId },
      include: {
        trader: {
          select: {
            address: true,
          },
        },
      },
    });

    // If no tracked traders, return empty
    if (trackedTraders.length === 0) {
      return NextResponse.json({
        trades: [],
        trackedCount: 0,
      });
    }

    // Build address to customName map
    const addressToCustomName: Record<string, string | null> = {};
    const addresses: string[] = [];

    for (const tt of trackedTraders) {
      const address = tt.trader.address.toLowerCase();
      addresses.push(address);
      addressToCustomName[address] = tt.customName;
    }

    // Query ClickHouse trades_recent table for trades from tracked addresses
    // Using IN clause with parameterized array
    const query = `
      SELECT
        id,
        trader_address,
        market_id,
        outcome_name,
        market_question,
        side,
        price,
        amount,
        usd_value,
        timestamp,
        smart_score
      FROM trades_recent
      WHERE lower(trader_address) IN ({addresses:Array(String)})
        AND usd_value >= {minAmount:Float64}
      ORDER BY timestamp DESC
      LIMIT {limit:UInt32}
    `;

    const trades = await queryClickHouse<ActivityTrade>(query, {
      addresses,
      minAmount: validMinAmount,
      limit: validLimit,
    });

    // Transform trades to include custom names and normalize values
    const tradesWithNames: ActivityTradeWithName[] = trades.map((trade) => {
      const normalizedAddress = trade.trader_address.toLowerCase();
      return {
        id: trade.id,
        trader_address: trade.trader_address,
        market_id: trade.market_id,
        outcome_name: trade.outcome_name,
        market_question: trade.market_question,
        // ClickHouse Enum8 returns string 'BUY' or 'SELL'
        side: trade.side === 'BUY' || trade.side === 'SELL' ? trade.side : 'BUY',
        // Convert numeric types from string if needed
        price: typeof trade.price === 'string' ? parseFloat(trade.price) : trade.price,
        amount: typeof trade.amount === 'string' ? parseFloat(trade.amount) : trade.amount,
        usd_value:
          typeof trade.usd_value === 'string' ? parseFloat(trade.usd_value) : trade.usd_value,
        // Ensure timestamp is ISO string
        timestamp:
          typeof trade.timestamp === 'string'
            ? trade.timestamp
            : new Date(trade.timestamp).toISOString(),
        smart_score:
          trade.smart_score === null
            ? null
            : typeof trade.smart_score === 'string'
              ? parseFloat(trade.smart_score)
              : trade.smart_score,
        // Add custom name from PostgreSQL
        customName: addressToCustomName[normalizedAddress] ?? null,
      };
    });

    return NextResponse.json({
      trades: tradesWithNames,
      trackedCount: trackedTraders.length,
    });
  } catch (error) {
    console.error(
      '[tracked-traders/activity] GET failed:',
      error instanceof Error ? error.message : error
    );

    return NextResponse.json(
      {
        error: 'Failed to fetch tracked traders activity',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
