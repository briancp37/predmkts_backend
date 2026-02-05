/**
 * Smart Trades API Route
 *
 * PRD #8 - Create Smart Trades API endpoint (ClickHouse)
 *
 * Handles GET requests to /api/trades/smart with:
 * - Query params: minScore, minAmount, limit
 * - Queries ClickHouse trades_recent table
 * - Filters by smart_score >= minScore and usd_value >= minAmount
 * - Orders by timestamp DESC
 *
 * Returns:
 * - 200: { trades } with filtered smart trades
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { queryClickHouse } from '@/lib/clickhouse';

/**
 * Trade row returned from ClickHouse trades_recent table
 */
interface SmartTrade {
  id: string;
  trader_address: string;
  market_id: string;
  outcome_id: string;
  outcome_name: string;
  market_question: string;
  side: 'BUY' | 'SELL';
  price: number;
  amount: number;
  usd_value: number;
  tx_hash: string;
  timestamp: string;
  smart_score: number | null;
}

/**
 * GET /api/trades/smart
 *
 * Fetch recent trades from smart traders (ClickHouse)
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse query params with defaults
    const minScore = parseFloat(searchParams.get('minScore') ?? '5');
    const minAmount = parseFloat(searchParams.get('minAmount') ?? '100');
    const limit = parseInt(searchParams.get('limit') ?? '100', 10);

    // Validate and clamp parameters
    const validMinScore = isNaN(minScore) ? 5 : Math.max(-100, Math.min(100, minScore));
    const validMinAmount = isNaN(minAmount) || minAmount < 0 ? 100 : minAmount;
    const validLimit = isNaN(limit) || limit < 1 ? 100 : Math.min(limit, 500);

    // Query ClickHouse trades_recent table for smart trades
    const query = `
      SELECT
        id,
        trader_address,
        market_id,
        outcome_id,
        outcome_name,
        market_question,
        side,
        price,
        amount,
        usd_value,
        tx_hash,
        timestamp,
        smart_score
      FROM trades_recent
      WHERE smart_score >= {minScore:Float64}
        AND usd_value >= {minAmount:Float64}
      ORDER BY timestamp DESC
      LIMIT {limit:UInt32}
    `;

    const trades = await queryClickHouse<SmartTrade>(query, {
      minScore: validMinScore,
      minAmount: validMinAmount,
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
      price: typeof trade.price === 'string' ? parseFloat(trade.price) : trade.price,
      amount: typeof trade.amount === 'string' ? parseFloat(trade.amount) : trade.amount,
      usd_value:
        typeof trade.usd_value === 'string' ? parseFloat(trade.usd_value) : trade.usd_value,
      smart_score:
        trade.smart_score === null
          ? null
          : typeof trade.smart_score === 'string'
            ? parseFloat(trade.smart_score)
            : trade.smart_score,
    }));

    return NextResponse.json({
      trades: normalizedTrades,
    });
  } catch (error) {
    console.error('[trades/smart] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch smart trades',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
