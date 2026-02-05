/**
 * Market Screener API Route
 *
 * PRD #6 - Create Market Screener API endpoint with time-based filters
 *
 * Handles GET requests to /api/markets/screener with:
 * - timeWindow: 6h, 12h, 24h, 7d (default: 24h)
 * - minVolume: minimum volume in USD
 * - maxVolume: maximum volume in USD
 * - minPriceChange: minimum price change percent (-100 to 100)
 * - maxPriceChange: maximum price change percent (-100 to 100)
 * - category: filter by market category
 * - resolved: filter by resolved status (true/false)
 * - sortBy: volume, priceChange, liquidity (default: volume)
 * - sortOrder: asc, desc (default: desc)
 * - limit: results limit (default: 50, max: 200)
 * - offset: pagination offset (default: 0)
 *
 * Calculates volume and price changes within timeWindow from ClickHouse market_stats_hourly.
 * Joins with PostgreSQL Market table for metadata (question, category, resolved, liquidity).
 *
 * Returns:
 * - 200: { markets, total, timeWindow, pagination }
 * - 400: Invalid query parameters
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { queryClickHouse } from '@/lib/clickhouse';
import { prisma } from '@/lib/prisma';

// Valid time windows and their ClickHouse interval expressions
const TIME_WINDOWS: Record<string, { interval: string; hours: number }> = {
  '6h': { interval: 'INTERVAL 6 HOUR', hours: 6 },
  '12h': { interval: 'INTERVAL 12 HOUR', hours: 12 },
  '24h': { interval: 'INTERVAL 24 HOUR', hours: 24 },
  '7d': { interval: 'INTERVAL 7 DAY', hours: 168 },
};

const VALID_SORT_BY = ['volume', 'priceChange', 'liquidity'];
const VALID_SORT_ORDER = ['asc', 'desc'];
const MAX_LIMIT = 200;
const DEFAULT_LIMIT = 50;

/**
 * Market stats row from ClickHouse
 */
interface MarketStatsRow {
  market_id: string;
  period_volume: string | number;
  start_price: string | number;
  end_price: string | number;
  trade_count: string | number;
}

/**
 * GET /api/markets/screener
 *
 * Fetch markets with volume and price change filtering
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse time window
    const timeWindow = searchParams.get('timeWindow') ?? '24h';
    if (!TIME_WINDOWS[timeWindow]) {
      return NextResponse.json(
        { error: `Invalid timeWindow. Must be one of: ${Object.keys(TIME_WINDOWS).join(', ')}` },
        { status: 400 }
      );
    }

    // Parse volume filters
    const minVolumeParam = searchParams.get('minVolume');
    const maxVolumeParam = searchParams.get('maxVolume');
    const minVolume = minVolumeParam ? parseFloat(minVolumeParam) : null;
    const maxVolume = maxVolumeParam ? parseFloat(maxVolumeParam) : null;

    if (minVolumeParam !== null && (isNaN(minVolume!) || minVolume! < 0)) {
      return NextResponse.json({ error: 'Invalid minVolume parameter' }, { status: 400 });
    }
    if (maxVolumeParam !== null && (isNaN(maxVolume!) || maxVolume! < 0)) {
      return NextResponse.json({ error: 'Invalid maxVolume parameter' }, { status: 400 });
    }

    // Parse price change filters
    const minPriceChangeParam = searchParams.get('minPriceChange');
    const maxPriceChangeParam = searchParams.get('maxPriceChange');
    const minPriceChange = minPriceChangeParam ? parseFloat(minPriceChangeParam) : null;
    const maxPriceChange = maxPriceChangeParam ? parseFloat(maxPriceChangeParam) : null;

    if (minPriceChangeParam !== null && isNaN(minPriceChange!)) {
      return NextResponse.json({ error: 'Invalid minPriceChange parameter' }, { status: 400 });
    }
    if (maxPriceChangeParam !== null && isNaN(maxPriceChange!)) {
      return NextResponse.json({ error: 'Invalid maxPriceChange parameter' }, { status: 400 });
    }

    // Parse category filter
    const category = searchParams.get('category');

    // Parse resolved filter
    const resolvedParam = searchParams.get('resolved');
    let resolved: boolean | undefined;
    if (resolvedParam !== null) {
      if (resolvedParam === 'true') {
        resolved = true;
      } else if (resolvedParam === 'false') {
        resolved = false;
      } else {
        return NextResponse.json(
          { error: 'Invalid resolved parameter (must be true or false)' },
          { status: 400 }
        );
      }
    }

    // Parse sort options
    const sortBy = searchParams.get('sortBy') ?? 'volume';
    const sortOrder = searchParams.get('sortOrder') ?? 'desc';

    if (!VALID_SORT_BY.includes(sortBy)) {
      return NextResponse.json(
        { error: `Invalid sortBy. Must be one of: ${VALID_SORT_BY.join(', ')}` },
        { status: 400 }
      );
    }
    if (!VALID_SORT_ORDER.includes(sortOrder)) {
      return NextResponse.json(
        { error: `Invalid sortOrder. Must be one of: ${VALID_SORT_ORDER.join(', ')}` },
        { status: 400 }
      );
    }

    // Parse pagination
    const limitParam = searchParams.get('limit');
    const offsetParam = searchParams.get('offset');

    let limit = DEFAULT_LIMIT;
    if (limitParam) {
      const parsedLimit = parseInt(limitParam, 10);
      if (isNaN(parsedLimit) || parsedLimit < 1) {
        return NextResponse.json({ error: 'Invalid limit parameter' }, { status: 400 });
      }
      limit = Math.min(parsedLimit, MAX_LIMIT);
    }

    let offset = 0;
    if (offsetParam) {
      const parsedOffset = parseInt(offsetParam, 10);
      if (isNaN(parsedOffset) || parsedOffset < 0) {
        return NextResponse.json({ error: 'Invalid offset parameter' }, { status: 400 });
      }
      offset = parsedOffset;
    }

    // Query ClickHouse for market stats within the time window
    // Using market_stats_hourly to calculate volume and price changes
    const { interval } = TIME_WINDOWS[timeWindow];

    const clickhouseQuery = `
      SELECT
        market_id,
        sum(volume) as period_volume,
        argMin(avg_price, hour) as start_price,
        argMax(avg_price, hour) as end_price,
        sum(trade_count) as trade_count
      FROM market_stats_hourly
      WHERE hour >= now() - ${interval}
      GROUP BY market_id
      HAVING period_volume > 0
    `;

    const marketStats = await queryClickHouse<MarketStatsRow>(clickhouseQuery);

    // Build a map of market_id -> stats with calculated price change
    const statsMap = new Map<
      string,
      {
        volume: number;
        startPrice: number;
        endPrice: number;
        priceChange: number;
        tradeCount: number;
      }
    >();

    for (const row of marketStats) {
      const volume =
        typeof row.period_volume === 'string' ? parseFloat(row.period_volume) : row.period_volume;
      const startPrice =
        typeof row.start_price === 'string' ? parseFloat(row.start_price) : row.start_price;
      const endPrice =
        typeof row.end_price === 'string' ? parseFloat(row.end_price) : row.end_price;
      const tradeCount =
        typeof row.trade_count === 'string' ? parseInt(row.trade_count, 10) : row.trade_count;

      // Calculate price change percentage
      // Handle case where start price is 0 to avoid division by zero
      let priceChange = 0;
      if (startPrice > 0) {
        priceChange = ((endPrice - startPrice) / startPrice) * 100;
      }

      statsMap.set(row.market_id, {
        volume,
        startPrice,
        endPrice,
        priceChange,
        tradeCount,
      });
    }

    // Get market IDs that passed ClickHouse filters
    let marketIds = Array.from(statsMap.keys());

    // Apply volume filters
    if (minVolume !== null) {
      marketIds = marketIds.filter((id) => statsMap.get(id)!.volume >= minVolume);
    }
    if (maxVolume !== null) {
      marketIds = marketIds.filter((id) => statsMap.get(id)!.volume <= maxVolume);
    }

    // Apply price change filters
    if (minPriceChange !== null) {
      marketIds = marketIds.filter((id) => statsMap.get(id)!.priceChange >= minPriceChange);
    }
    if (maxPriceChange !== null) {
      marketIds = marketIds.filter((id) => statsMap.get(id)!.priceChange <= maxPriceChange);
    }

    // Fetch markets from PostgreSQL that match our filtered IDs
    // Note: polymarketId in PostgreSQL maps to market_id in ClickHouse
    const marketsWhere: {
      polymarketId?: { in: string[] };
      category?: string;
      resolved?: boolean;
    } = {};

    if (marketIds.length > 0) {
      marketsWhere.polymarketId = { in: marketIds };
    }
    if (category) {
      marketsWhere.category = category;
    }
    if (resolved !== undefined) {
      marketsWhere.resolved = resolved;
    }

    // If we have no market IDs after filtering, return empty result
    if (marketIds.length === 0) {
      return NextResponse.json({
        markets: [],
        total: 0,
        timeWindow,
        pagination: { limit, offset },
      });
    }

    // Fetch all matching markets from PostgreSQL (we'll sort and paginate in memory)
    const markets = await prisma.market.findMany({
      where: marketsWhere,
      select: {
        id: true,
        polymarketId: true,
        slug: true,
        question: true,
        category: true,
        endDate: true,
        resolved: true,
        liquidity: true,
      },
    });

    // Combine PostgreSQL data with ClickHouse stats
    const combinedMarkets = markets
      .map((market) => {
        const stats = statsMap.get(market.polymarketId);
        if (!stats) return null;

        return {
          id: market.id,
          polymarketId: market.polymarketId,
          slug: market.slug,
          question: market.question,
          category: market.category,
          endDate: market.endDate,
          resolved: market.resolved,
          liquidity: market.liquidity,
          volume: stats.volume,
          priceChange: stats.priceChange,
          startPrice: stats.startPrice,
          endPrice: stats.endPrice,
          tradeCount: stats.tradeCount,
        };
      })
      .filter((m) => m !== null);

    // Apply sorting
    const sortedMarkets = combinedMarkets.sort((a, b) => {
      let aValue: number;
      let bValue: number;

      switch (sortBy) {
        case 'volume':
          aValue = a.volume;
          bValue = b.volume;
          break;
        case 'priceChange':
          aValue = a.priceChange;
          bValue = b.priceChange;
          break;
        case 'liquidity':
          aValue = a.liquidity;
          bValue = b.liquidity;
          break;
        default:
          aValue = a.volume;
          bValue = b.volume;
      }

      return sortOrder === 'desc' ? bValue - aValue : aValue - bValue;
    });

    // Apply pagination
    const total = sortedMarkets.length;
    const paginatedMarkets = sortedMarkets.slice(offset, offset + limit);

    return NextResponse.json({
      markets: paginatedMarkets,
      total,
      timeWindow,
      pagination: { limit, offset },
    });
  } catch (error) {
    console.error('[markets/screener] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch market screener data',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
