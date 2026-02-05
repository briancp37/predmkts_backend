/**
 * Whale Trades API Route
 *
 * PRD #9 - Create Whale Trades API endpoint (ClickHouse)
 *
 * Handles GET requests to /api/whales/trades with:
 * - Query params: minUsd (default 1000), limit (default 100)
 * - Queries ClickHouse whale_trades table
 * - Filters by usd_value >= minUsd
 * - Orders by timestamp DESC
 *
 * Returns:
 * - 200: { trades } with filtered whale trades
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { queryClickHouse } from '@/lib/clickhouse';

/**
 * Trade row returned from ClickHouse whale_trades table
 */
interface WhaleTrade {
  id: string;
  trader_address: string;
  market_id: string;
  market_question: string;
  side: 'BUY' | 'SELL';
  usd_value: number;
  price: number;
  wallet_age_days: number;
  timestamp: string;
}

/**
 * GET /api/whales/trades
 *
 * Fetch large trades from the whale_trades table (ClickHouse)
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse query params with defaults
    const minUsd = parseFloat(searchParams.get('minUsd') ?? '1000');
    const limit = parseInt(searchParams.get('limit') ?? '100', 10);

    // Validate and clamp parameters
    const validMinUsd = isNaN(minUsd) || minUsd < 0 ? 1000 : minUsd;
    const validLimit = isNaN(limit) || limit < 1 ? 100 : Math.min(limit, 500);

    // Query ClickHouse whale_trades table
    const query = `
      SELECT
        id,
        trader_address,
        market_id,
        market_question,
        side,
        usd_value,
        price,
        wallet_age_days,
        timestamp
      FROM whale_trades
      WHERE usd_value >= {minUsd:Float64}
      ORDER BY timestamp DESC
      LIMIT {limit:UInt32}
    `;

    const trades = await queryClickHouse<WhaleTrade>(query, {
      minUsd: validMinUsd,
      limit: validLimit,
    });

    // Transform trades to normalize side enum and format timestamp
    const normalizedTrades = trades.map((trade) => ({
      ...trade,
      // ClickHouse Enum8 returns string 'BUY' or 'SELL'
      side: trade.side === 'BUY' || trade.side === 'SELL' ? trade.side : 'BUY',
      // Ensure timestamp is ISO string
      timestamp:
        typeof trade.timestamp === 'string'
          ? trade.timestamp
          : new Date(trade.timestamp).toISOString(),
      // Convert numeric types from string if needed
      usd_value:
        typeof trade.usd_value === 'string' ? parseFloat(trade.usd_value) : trade.usd_value,
      price: typeof trade.price === 'string' ? parseFloat(trade.price) : trade.price,
      wallet_age_days:
        typeof trade.wallet_age_days === 'string'
          ? parseInt(trade.wallet_age_days, 10)
          : trade.wallet_age_days,
    }));

    return NextResponse.json({
      trades: normalizedTrades,
    });
  } catch (error) {
    console.error('[whales/trades] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch whale trades',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
