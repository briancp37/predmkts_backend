/**
 * Market Map API Route
 *
 * PRD #7 - Create Market Map data endpoint for treemap visualization
 *
 * Handles GET requests to /api/markets/map with:
 * - timeWindow: 6h, 12h, 24h, 7d (default: 24h)
 * - sizeMetric: volume, liquidity, trades (default: volume)
 * - colorMetric: priceChange, smartMoneyFlow (default: priceChange)
 *
 * Returns hierarchical data structure for treemap visualization:
 * - Groups markets by category
 * - Calculates size_value based on sizeMetric
 * - Calculates color_value based on colorMetric
 *
 * Returns:
 * - 200: { data: hierarchical_structure, sizeMetric, colorMetric, timeWindow }
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

const VALID_SIZE_METRICS = ['volume', 'liquidity', 'trades'];
const VALID_COLOR_METRICS = ['priceChange', 'smartMoneyFlow'];

/**
 * Market stats row from ClickHouse
 */
interface MarketStatsRow {
  market_id: string;
  period_volume: string | number;
  period_trades: string | number;
  avg_price: string | number;
  price_range: string | number;
  start_price: string | number;
  end_price: string | number;
}

/**
 * Smart money stats row from ClickHouse
 */
interface SmartMoneyRow {
  market_id: string;
  smart_buy_volume: string | number;
  smart_sell_volume: string | number;
}

/**
 * Market node in the treemap hierarchy
 */
interface MarketNode {
  name: string;
  value: number;
  color: number;
  market_id: string;
  slug: string | null;
}

/**
 * Category node in the treemap hierarchy
 */
interface CategoryNode {
  name: string;
  children: MarketNode[];
}

/**
 * Root node of the treemap hierarchy
 */
interface TreemapData {
  name: string;
  children: CategoryNode[];
}

/**
 * GET /api/markets/map
 *
 * Fetch hierarchical market data for treemap visualization
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

    // Parse size metric
    const sizeMetric = searchParams.get('sizeMetric') ?? 'volume';
    if (!VALID_SIZE_METRICS.includes(sizeMetric)) {
      return NextResponse.json(
        { error: `Invalid sizeMetric. Must be one of: ${VALID_SIZE_METRICS.join(', ')}` },
        { status: 400 }
      );
    }

    // Parse color metric
    const colorMetric = searchParams.get('colorMetric') ?? 'priceChange';
    if (!VALID_COLOR_METRICS.includes(colorMetric)) {
      return NextResponse.json(
        { error: `Invalid colorMetric. Must be one of: ${VALID_COLOR_METRICS.join(', ')}` },
        { status: 400 }
      );
    }

    const { interval } = TIME_WINDOWS[timeWindow];

    // Query ClickHouse for market stats within the time window
    const clickhouseQuery = `
      SELECT
        market_id,
        sum(volume) as period_volume,
        sum(trade_count) as period_trades,
        avg(avg_price) as avg_price,
        max(high_price) - min(low_price) as price_range,
        argMin(avg_price, hour) as start_price,
        argMax(avg_price, hour) as end_price
      FROM market_stats_hourly
      WHERE hour >= now() - ${interval}
      GROUP BY market_id
      HAVING period_volume > 0
    `;

    const marketStats = await queryClickHouse<MarketStatsRow>(clickhouseQuery);

    // Build a map of market_id -> stats
    const statsMap = new Map<
      string,
      {
        volume: number;
        trades: number;
        avgPrice: number;
        priceChange: number;
      }
    >();

    for (const row of marketStats) {
      const volume =
        typeof row.period_volume === 'string' ? parseFloat(row.period_volume) : row.period_volume;
      const trades =
        typeof row.period_trades === 'string' ? parseInt(row.period_trades, 10) : row.period_trades;
      const avgPrice =
        typeof row.avg_price === 'string' ? parseFloat(row.avg_price) : row.avg_price;
      const startPrice =
        typeof row.start_price === 'string' ? parseFloat(row.start_price) : row.start_price;
      const endPrice =
        typeof row.end_price === 'string' ? parseFloat(row.end_price) : row.end_price;

      // Calculate price change percentage
      let priceChange = 0;
      if (startPrice > 0) {
        priceChange = ((endPrice - startPrice) / startPrice) * 100;
      }

      statsMap.set(row.market_id, {
        volume,
        trades,
        avgPrice,
        priceChange,
      });
    }

    // If colorMetric is smartMoneyFlow, query trades_recent for smart trader volume
    const smartMoneyMap = new Map<string, number>();
    if (colorMetric === 'smartMoneyFlow') {
      const smartMoneyQuery = `
        SELECT
          market_id,
          sumIf(usd_value, side = 'BUY') as smart_buy_volume,
          sumIf(usd_value, side = 'SELL') as smart_sell_volume
        FROM trades_recent
        WHERE timestamp >= now() - ${interval}
          AND smart_score >= 20
        GROUP BY market_id
      `;

      const smartMoneyStats = await queryClickHouse<SmartMoneyRow>(smartMoneyQuery);

      for (const row of smartMoneyStats) {
        const buyVolume =
          typeof row.smart_buy_volume === 'string'
            ? parseFloat(row.smart_buy_volume)
            : row.smart_buy_volume;
        const sellVolume =
          typeof row.smart_sell_volume === 'string'
            ? parseFloat(row.smart_sell_volume)
            : row.smart_sell_volume;

        // Smart money flow: positive = net buying, negative = net selling
        // Normalize to -100 to +100 scale based on buy/sell ratio
        const totalSmartVolume = buyVolume + sellVolume;
        let flow = 0;
        if (totalSmartVolume > 0) {
          // Calculate net flow as percentage: (buy - sell) / total * 100
          flow = ((buyVolume - sellVolume) / totalSmartVolume) * 100;
        }
        smartMoneyMap.set(row.market_id, flow);
      }
    }

    // Get market IDs from stats
    const marketIds = Array.from(statsMap.keys());

    if (marketIds.length === 0) {
      return NextResponse.json({
        data: { name: 'Markets', children: [] },
        sizeMetric,
        colorMetric,
        timeWindow,
      });
    }

    // Fetch markets from PostgreSQL with metadata and current liquidity
    const markets = await prisma.market.findMany({
      where: {
        polymarketId: { in: marketIds },
        resolved: false, // Only show active markets in treemap
      },
      select: {
        id: true,
        polymarketId: true,
        slug: true,
        question: true,
        category: true,
        liquidity: true,
      },
    });

    // Group markets by category
    const categoryMap = new Map<string, MarketNode[]>();

    for (const market of markets) {
      const stats = statsMap.get(market.polymarketId);
      if (!stats) continue;

      // Calculate size value based on sizeMetric
      let sizeValue: number;
      switch (sizeMetric) {
        case 'volume':
          sizeValue = stats.volume;
          break;
        case 'liquidity':
          sizeValue = market.liquidity;
          break;
        case 'trades':
          sizeValue = stats.trades;
          break;
        default:
          sizeValue = stats.volume;
      }

      // Skip markets with 0 size value (wouldn't be visible in treemap)
      if (sizeValue <= 0) continue;

      // Calculate color value based on colorMetric
      let colorValue: number;
      switch (colorMetric) {
        case 'priceChange':
          colorValue = stats.priceChange;
          break;
        case 'smartMoneyFlow':
          colorValue = smartMoneyMap.get(market.polymarketId) ?? 0;
          break;
        default:
          colorValue = stats.priceChange;
      }

      const category = market.category || 'Other';
      const marketNode: MarketNode = {
        name: market.question,
        value: sizeValue,
        color: colorValue,
        market_id: market.polymarketId,
        slug: market.slug,
      };

      if (!categoryMap.has(category)) {
        categoryMap.set(category, []);
      }
      categoryMap.get(category)!.push(marketNode);
    }

    // Build hierarchical structure
    const children: CategoryNode[] = [];
    for (const [categoryName, marketNodes] of categoryMap) {
      // Sort markets by size value descending within each category
      marketNodes.sort((a, b) => b.value - a.value);

      children.push({
        name: categoryName,
        children: marketNodes,
      });
    }

    // Sort categories by total size value descending
    children.sort((a, b) => {
      const aTotal = a.children.reduce((sum, m) => sum + m.value, 0);
      const bTotal = b.children.reduce((sum, m) => sum + m.value, 0);
      return bTotal - aTotal;
    });

    const treemapData: TreemapData = {
      name: 'Markets',
      children,
    };

    return NextResponse.json({
      data: treemapData,
      sizeMetric,
      colorMetric,
      timeWindow,
    });
  } catch (error) {
    console.error('[markets/map] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch market map data',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
