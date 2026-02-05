/**
 * Historical Trades API Route
 *
 * PRD #3 - Create API endpoint to query historical trades from S3
 *
 * Handles GET requests to /api/trades/historical with:
 * - Query params: trader_address, market_id, start_date, end_date, limit
 * - Queries S3 Parquet files via ClickHouse s3() function
 * - Joins with markets_metadata for market info enrichment
 * - Rate limited: 10 requests/minute per user
 *
 * Validation:
 * - Date range max 90 days
 * - Queries > 7 days require trader_address or market_id filter
 *
 * Returns:
 * - 200: { trades, total, dateRange, queryTimeMs }
 * - 400: Validation error
 * - 429: Rate limit exceeded
 * - 500: Internal server error
 *
 * Response headers:
 * - X-S3-Partitions-Scanned: Number of date partitions scanned
 * - X-RateLimit-Remaining: Remaining requests in window
 * - X-RateLimit-Reset: Unix timestamp when limit resets
 */

import { NextRequest, NextResponse } from 'next/server';
import { queryHistoricalTrades, HistoricalTrade } from '@/lib/clickhouse-s3';
import { queryClickHouse } from '@/lib/clickhouse';
import { checkRateLimit, getRateLimitKey } from '@/lib/rate-limit';

// Rate limit: 10 requests per minute
const RATE_LIMIT = 10;
const RATE_LIMIT_WINDOW_MS = 60 * 1000;

// Max date range: 90 days
const MAX_DATE_RANGE_DAYS = 90;

// Date range requiring filter: 7 days
const REQUIRE_FILTER_DAYS = 7;

/**
 * Market metadata from ClickHouse markets_metadata table
 */
interface MarketMetadata {
  market_id: string;
  question: string;
  slug: string;
  category: string;
  outcome_yes: string;
  outcome_no: string;
}

/**
 * Enriched historical trade with market info
 */
interface EnrichedHistoricalTrade extends HistoricalTrade {
  market_question?: string;
  market_slug?: string;
  market_category?: string;
  trader_address: string;
  trader_side: 'BUY' | 'SELL';
}

/**
 * Parse a date string to Date object
 */
function parseDate(dateStr: string | null): Date | null {
  if (!dateStr) return null;

  // Try ISO date format (YYYY-MM-DD)
  const parsed = new Date(dateStr);
  if (isNaN(parsed.getTime())) {
    return null;
  }

  return parsed;
}

/**
 * Calculate the number of days between two dates
 */
function daysBetween(start: Date, end: Date): number {
  const diffMs = end.getTime() - start.getTime();
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
}

/**
 * Fetch market metadata for a list of market IDs
 */
async function getMarketMetadata(marketIds: string[]): Promise<Map<string, MarketMetadata>> {
  if (marketIds.length === 0) {
    return new Map();
  }

  // Deduplicate market IDs
  const uniqueIds = [...new Set(marketIds)];

  try {
    const query = `
      SELECT
        market_id,
        question,
        slug,
        category,
        outcome_yes,
        outcome_no
      FROM markets_metadata
      WHERE market_id IN ({marketIds:Array(String)})
    `;

    const results = await queryClickHouse<MarketMetadata>(query, {
      marketIds: uniqueIds,
    });

    const metadataMap = new Map<string, MarketMetadata>();
    for (const row of results) {
      metadataMap.set(row.market_id, row);
    }

    return metadataMap;
  } catch (error) {
    console.warn('[trades/historical] Failed to fetch market metadata:', error);
    return new Map();
  }
}

/**
 * Transform raw historical trade to enriched format
 */
function enrichTrade(
  trade: HistoricalTrade,
  traderAddress: string | undefined,
  metadata: Map<string, MarketMetadata>
): EnrichedHistoricalTrade {
  const marketMeta = metadata.get(trade.market_id);

  // Determine which side of the trade the queried address is on
  let traderAddr: string;
  let traderSide: 'BUY' | 'SELL';

  if (traderAddress) {
    const normalizedAddr = traderAddress.toLowerCase();
    if (trade.maker.toLowerCase() === normalizedAddr) {
      traderAddr = trade.maker;
      traderSide = trade.maker_direction as 'BUY' | 'SELL';
    } else if (trade.taker.toLowerCase() === normalizedAddr) {
      traderAddr = trade.taker;
      traderSide = trade.taker_direction as 'BUY' | 'SELL';
    } else {
      // Fallback - shouldn't happen if filters worked correctly
      traderAddr = trade.taker;
      traderSide = trade.taker_direction as 'BUY' | 'SELL';
    }
  } else {
    // No specific trader - default to taker perspective
    traderAddr = trade.taker;
    traderSide = trade.taker_direction as 'BUY' | 'SELL';
  }

  return {
    ...trade,
    market_question: marketMeta?.question,
    market_slug: marketMeta?.slug,
    market_category: marketMeta?.category,
    trader_address: traderAddr,
    trader_side: traderSide,
    // Convert numeric fields
    price: typeof trade.price === 'string' ? parseFloat(trade.price) : trade.price,
    usd_amount:
      typeof trade.usd_amount === 'string' ? parseFloat(trade.usd_amount) : trade.usd_amount,
    token_amount:
      typeof trade.token_amount === 'string' ? parseFloat(trade.token_amount) : trade.token_amount,
  };
}

/**
 * GET /api/trades/historical
 *
 * Query historical trades from S3 Parquet files via ClickHouse
 */
export async function GET(request: NextRequest) {
  // Check rate limit
  const rateLimitKey = `historical:${getRateLimitKey(request)}`;
  const rateLimit = checkRateLimit(rateLimitKey, RATE_LIMIT, RATE_LIMIT_WINDOW_MS);

  if (!rateLimit.allowed) {
    return NextResponse.json(
      {
        error: 'Rate limit exceeded',
        message: `Maximum ${RATE_LIMIT} requests per minute. Try again in ${Math.ceil((rateLimit.resetAt - Date.now()) / 1000)} seconds.`,
      },
      {
        status: 429,
        headers: {
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Reset': rateLimit.resetAt.toString(),
          'Retry-After': Math.ceil((rateLimit.resetAt - Date.now()) / 1000).toString(),
        },
      }
    );
  }

  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse query parameters
    const traderAddress = searchParams.get('trader_address');
    const marketId = searchParams.get('market_id');
    const startDateStr = searchParams.get('start_date');
    const endDateStr = searchParams.get('end_date');
    const limitStr = searchParams.get('limit');

    // Validate required date parameters
    if (!startDateStr || !endDateStr) {
      return NextResponse.json(
        {
          error: 'Missing required parameters',
          message: 'Both start_date and end_date are required (format: YYYY-MM-DD)',
        },
        { status: 400 }
      );
    }

    // Parse dates
    const startDate = parseDate(startDateStr);
    const endDate = parseDate(endDateStr);

    if (!startDate) {
      return NextResponse.json(
        {
          error: 'Invalid start_date',
          message: 'start_date must be a valid date (format: YYYY-MM-DD)',
        },
        { status: 400 }
      );
    }

    if (!endDate) {
      return NextResponse.json(
        {
          error: 'Invalid end_date',
          message: 'end_date must be a valid date (format: YYYY-MM-DD)',
        },
        { status: 400 }
      );
    }

    // Validate date range
    if (startDate > endDate) {
      return NextResponse.json(
        {
          error: 'Invalid date range',
          message: 'start_date must be before or equal to end_date',
        },
        { status: 400 }
      );
    }

    const dayRange = daysBetween(startDate, endDate);

    if (dayRange > MAX_DATE_RANGE_DAYS) {
      return NextResponse.json(
        {
          error: 'Date range too large',
          message: `Maximum date range is ${MAX_DATE_RANGE_DAYS} days. Your range: ${dayRange} days.`,
        },
        { status: 400 }
      );
    }

    // Require filter for queries > 7 days to prevent expensive full scans
    if (dayRange > REQUIRE_FILTER_DAYS && !traderAddress && !marketId) {
      return NextResponse.json(
        {
          error: 'Filter required for large date range',
          message: `Queries spanning more than ${REQUIRE_FILTER_DAYS} days require either trader_address or market_id filter to prevent expensive full scans.`,
        },
        { status: 400 }
      );
    }

    // Validate trader address format if provided
    if (traderAddress && !traderAddress.match(/^0x[a-fA-F0-9]{40}$/)) {
      return NextResponse.json(
        {
          error: 'Invalid trader_address',
          message:
            'trader_address must be a valid Ethereum address (0x followed by 40 hex characters)',
        },
        { status: 400 }
      );
    }

    // Parse and validate limit
    const limit = limitStr ? parseInt(limitStr, 10) : 100;
    const validLimit = isNaN(limit) || limit < 1 ? 100 : Math.min(limit, 1000);

    // Query historical trades from S3
    const result = await queryHistoricalTrades({
      startDate,
      endDate,
      traderAddress: traderAddress || undefined,
      marketId: marketId || undefined,
      limit: validLimit,
    });

    // Get market metadata for enrichment
    const marketIds = result.trades.map((t) => t.market_id);
    const marketMetadata = await getMarketMetadata(marketIds);

    // Enrich trades with market info
    const enrichedTrades = result.trades.map((trade) =>
      enrichTrade(trade, traderAddress || undefined, marketMetadata)
    );

    // Build response
    const response = NextResponse.json({
      trades: enrichedTrades,
      total: enrichedTrades.length,
      dateRange: {
        start: startDate.toISOString().split('T')[0],
        end: endDate.toISOString().split('T')[0],
      },
      queryTimeMs: result.queryTimeMs,
    });

    // Add rate limit and S3 info headers
    response.headers.set('X-S3-Partitions-Scanned', result.partitionsScanned.toString());
    response.headers.set('X-RateLimit-Remaining', rateLimit.remaining.toString());
    response.headers.set('X-RateLimit-Reset', rateLimit.resetAt.toString());

    return response;
  } catch (error) {
    console.error(
      '[trades/historical] GET failed:',
      error instanceof Error ? error.message : error
    );

    // Check for AWS credentials error
    if (error instanceof Error && error.message.includes('AWS credentials')) {
      return NextResponse.json(
        {
          error: 'Service configuration error',
          message: 'Historical trade data is not available. AWS credentials not configured.',
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      {
        error: 'Failed to fetch historical trades',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
