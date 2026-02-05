/**
 * Markets Advanced API Route
 *
 * PRD #1 - Create Markets Advanced API endpoint with CLOB bid/ask data and comprehensive filtering
 *
 * Handles GET requests to /api/markets/advanced with:
 * - category: Filter by market category
 * - sortBy: volume, liquidity, spread (default: volume)
 * - sortOrder: asc, desc (default: desc)
 * - minVolume, maxVolume: Volume range filter
 * - minLiquidity, maxLiquidity: Liquidity range filter
 * - minSpread, maxSpread: Spread percentage range filter
 * - minSpreadCents, maxSpreadCents: Spread in cents range filter
 * - timeRemaining: all, 1d, 7d, 30d (filter by time until end date)
 * - createdDate: all, 1d, 7d, 30d (filter by market creation date)
 * - minChange, maxChange: 24h price change percentage filter
 * - tags: Comma-separated list of tags to filter by
 * - limit: Results limit (default: 25, max: 1000)
 * - offset: Pagination offset (default: 0)
 * - page: Alternative pagination by page number
 *
 * Fetches bid/ask data from Polymarket CLOB API using batch endpoint (POST /books).
 * Fetches 24h volume change from ClickHouse market_stats_hourly.
 *
 * Returns:
 * - 200: { markets, total, pagination }
 * - 400: Invalid query parameters
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { Prisma } from '@prisma/client';

// Pagination limits
const MAX_LIMIT = 1000;
const DEFAULT_LIMIT = 25;

// Valid sort options
const VALID_SORT_BY = ['volume', 'liquidity', 'spread'] as const;
const VALID_SORT_ORDER = ['asc', 'desc'] as const;

// Time filter options
const TIME_FILTERS = ['all', '1d', '7d', '30d'] as const;

type SortBy = (typeof VALID_SORT_BY)[number];
type SortOrder = (typeof VALID_SORT_ORDER)[number];
type TimeFilter = (typeof TIME_FILTERS)[number];

/**
 * Combined market data returned by the API
 */
interface AdvancedMarketData {
  id: string;
  polymarketId: string;
  conditionId: string | null;
  slug: string | null;
  question: string;
  description: string | null;
  category: string | null;
  endDate: string | null;
  resolved: boolean;
  totalVolume: number;
  liquidity: number;
  createdAt: string;
  imageUrl: string | null;
  outcomes: {
    id: string;
    tokenId: string;
    outcomeName: string;
    currentPrice: number;
    volume: number;
  }[];
  // CLOB data
  bid: number | null;
  ask: number | null;
  spread: number | null;
  spreadPercent: number | null;
  spreadCents: number | null;
  // 24h stats
  volume24h: number;
  priceChange24h: number;
}

/**
 * Parse numeric query parameter
 */
function parseNumericParam(value: string | null, paramName: string): number | null {
  if (value === null) return null;
  const parsed = parseFloat(value);
  if (isNaN(parsed)) {
    throw new Error(`Invalid ${paramName} parameter`);
  }
  return parsed;
}

/**
 * Parse pagination parameters
 */
function parsePaginationParams(
  searchParams: URLSearchParams
): { limit: number; offset: number } | { error: string } {
  const limitParam = searchParams.get('limit');
  const offsetParam = searchParams.get('offset');
  const pageParam = searchParams.get('page');

  let limit = DEFAULT_LIMIT;
  if (limitParam) {
    const parsedLimit = parseInt(limitParam, 10);
    if (isNaN(parsedLimit) || parsedLimit < 1) {
      return { error: 'Invalid limit parameter' };
    }
    limit = Math.min(parsedLimit, MAX_LIMIT);
  }

  let offset = 0;
  if (pageParam) {
    const parsedPage = parseInt(pageParam, 10);
    if (isNaN(parsedPage) || parsedPage < 1) {
      return { error: 'Invalid page parameter' };
    }
    offset = (parsedPage - 1) * limit;
  } else if (offsetParam) {
    const parsedOffset = parseInt(offsetParam, 10);
    if (isNaN(parsedOffset) || parsedOffset < 0) {
      return { error: 'Invalid offset parameter' };
    }
    offset = parsedOffset;
  }

  return { limit, offset };
}

/**
 * Get date threshold for time filter
 */
function getTimeFilterDate(filter: TimeFilter): Date | null {
  if (filter === 'all') return null;

  const now = new Date();
  switch (filter) {
    case '1d':
      return new Date(now.getTime() - 24 * 60 * 60 * 1000);
    case '7d':
      return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    case '30d':
      return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    default:
      return null;
  }
}

/**
 * GET /api/markets/advanced
 *
 * Fetch markets with CLOB bid/ask data and comprehensive filtering
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    // Parse pagination
    const pagination = parsePaginationParams(searchParams);
    if ('error' in pagination) {
      return NextResponse.json({ error: pagination.error }, { status: 400 });
    }
    const { limit, offset } = pagination;

    // Parse category filter
    const category = searchParams.get('category');

    // Parse sort options
    const sortByParam = searchParams.get('sortBy') ?? 'volume';
    const sortOrderParam = searchParams.get('sortOrder') ?? 'desc';

    if (!VALID_SORT_BY.includes(sortByParam as SortBy)) {
      return NextResponse.json(
        { error: `Invalid sortBy. Must be one of: ${VALID_SORT_BY.join(', ')}` },
        { status: 400 }
      );
    }
    if (!VALID_SORT_ORDER.includes(sortOrderParam as SortOrder)) {
      return NextResponse.json(
        { error: `Invalid sortOrder. Must be one of: ${VALID_SORT_ORDER.join(', ')}` },
        { status: 400 }
      );
    }

    const sortBy = sortByParam as SortBy;
    const sortOrder = sortOrderParam as SortOrder;

    // Parse range filters
    let minVolume: number | null = null;
    let maxVolume: number | null = null;
    let minLiquidity: number | null = null;
    let maxLiquidity: number | null = null;
    let minSpread: number | null = null;
    let maxSpread: number | null = null;
    let minSpreadCents: number | null = null;
    let maxSpreadCents: number | null = null;
    let minChange: number | null = null;
    let maxChange: number | null = null;

    try {
      minVolume = parseNumericParam(searchParams.get('minVolume'), 'minVolume');
      maxVolume = parseNumericParam(searchParams.get('maxVolume'), 'maxVolume');
      minLiquidity = parseNumericParam(searchParams.get('minLiquidity'), 'minLiquidity');
      maxLiquidity = parseNumericParam(searchParams.get('maxLiquidity'), 'maxLiquidity');
      minSpread = parseNumericParam(searchParams.get('minSpread'), 'minSpread');
      maxSpread = parseNumericParam(searchParams.get('maxSpread'), 'maxSpread');
      minSpreadCents = parseNumericParam(searchParams.get('minSpreadCents'), 'minSpreadCents');
      maxSpreadCents = parseNumericParam(searchParams.get('maxSpreadCents'), 'maxSpreadCents');
      minChange = parseNumericParam(searchParams.get('minChange'), 'minChange');
      maxChange = parseNumericParam(searchParams.get('maxChange'), 'maxChange');
    } catch (error) {
      return NextResponse.json(
        { error: error instanceof Error ? error.message : 'Invalid parameter' },
        { status: 400 }
      );
    }

    // Parse time filters
    const timeRemainingParam = searchParams.get('timeRemaining') ?? 'all';
    const createdDateParam = searchParams.get('createdDate') ?? 'all';

    if (!TIME_FILTERS.includes(timeRemainingParam as TimeFilter)) {
      return NextResponse.json(
        { error: `Invalid timeRemaining. Must be one of: ${TIME_FILTERS.join(', ')}` },
        { status: 400 }
      );
    }
    if (!TIME_FILTERS.includes(createdDateParam as TimeFilter)) {
      return NextResponse.json(
        { error: `Invalid createdDate. Must be one of: ${TIME_FILTERS.join(', ')}` },
        { status: 400 }
      );
    }

    const timeRemaining = timeRemainingParam as TimeFilter;
    const createdDate = createdDateParam as TimeFilter;

    // Parse tags filter
    const tagsParam = searchParams.get('tags');
    const tags = tagsParam ? tagsParam.split(',').map((t) => t.trim().toLowerCase()) : null;

    // Build Prisma where clause for initial filtering
    const where: Prisma.MarketWhereInput = {
      resolved: false, // Default to active markets
    };

    if (category) {
      where.category = category;
    }

    // Apply liquidity filters at database level
    if (minLiquidity !== null || maxLiquidity !== null) {
      where.liquidity = {};
      if (minLiquidity !== null) {
        where.liquidity.gte = minLiquidity;
      }
      if (maxLiquidity !== null) {
        where.liquidity.lte = maxLiquidity;
      }
    }

    // Apply total volume filters at database level
    if (minVolume !== null || maxVolume !== null) {
      where.totalVolume = {};
      if (minVolume !== null) {
        where.totalVolume.gte = minVolume;
      }
      if (maxVolume !== null) {
        where.totalVolume.lte = maxVolume;
      }
    }

    // Apply time remaining filter (filter by endDate)
    if (timeRemaining !== 'all') {
      const now = new Date();
      const threshold = getTimeFilterDate(timeRemaining);
      if (threshold) {
        // Markets ending within the time window
        const futureThreshold = new Date(now.getTime() + (threshold.getTime() - now.getTime()) * -1);
        where.endDate = {
          gte: now,
          lte: futureThreshold,
        };
      }
    }

    // Apply created date filter
    if (createdDate !== 'all') {
      const threshold = getTimeFilterDate(createdDate);
      if (threshold) {
        where.createdAt = {
          gte: threshold,
        };
      }
    }

    // Apply tag filtering using proper Tag/MarketTag tables (PRD #15)
    if (tags && tags.length > 0) {
      where.tags = {
        some: {
          tag: {
            slug: { in: tags },
          },
        },
      };
    }

    // Determine sort field for Prisma (only volume and liquidity can be sorted at DB level)
    // Spread sorting requires CLOB data and is handled differently
    const canSortAtDbLevel = sortBy === 'volume' || sortBy === 'liquidity';
    const prismaOrderBy: { totalVolume?: 'asc' | 'desc'; liquidity?: 'asc' | 'desc' } = {};

    if (canSortAtDbLevel) {
      if (sortBy === 'volume') {
        prismaOrderBy.totalVolume = sortOrder;
      } else if (sortBy === 'liquidity') {
        prismaOrderBy.liquidity = sortOrder;
      }
    } else {
      // Default to volume desc for spread sorting (we'll re-sort after CLOB data)
      prismaOrderBy.totalVolume = 'desc';
    }

    // Get total count for pagination
    const total = await prisma.market.count({ where });

    if (total === 0) {
      return NextResponse.json({
        markets: [],
        total: 0,
        pagination: {
          limit,
          offset,
          page: Math.floor(offset / limit) + 1,
          totalPages: 0,
        },
      });
    }

    // Fetch paginated markets from PostgreSQL
    // For spread sorting, we fetch more markets (up to 200) to allow post-CLOB sorting
    const fetchLimit = canSortAtDbLevel ? limit : Math.min(200, total);
    const fetchOffset = canSortAtDbLevel ? offset : 0;

    const markets = await prisma.market.findMany({
      where,
      include: {
        outcomes: {
          select: {
            id: true,
            tokenId: true,
            outcomeName: true,
            currentPrice: true,
            volume: true,
          },
        },
        event: {
          select: {
            imageUrl: true,
          },
        },
      },
      orderBy: prismaOrderBy,
      skip: fetchOffset,
      take: fetchLimit,
    });

    if (markets.length === 0) {
      return NextResponse.json({
        markets: [],
        total,
        pagination: {
          limit,
          offset,
          page: Math.floor(offset / limit) + 1,
          totalPages: Math.ceil(total / limit),
        },
      });
    }

    // Collect token IDs for CLOB batch request
    const tokenIds: string[] = [];
    const marketTokenMap = new Map<string, string>(); // marketId -> first tokenId

    for (const market of markets) {
      const firstOutcome = market.outcomes[0];
      if (firstOutcome?.tokenId) {
        tokenIds.push(firstOutcome.tokenId);
        marketTokenMap.set(market.id, firstOutcome.tokenId);
      }
    }

    // Fetch CLOB bid/ask data and ClickHouse stats in parallel
    const marketIds = markets.map((m) => m.polymarketId);

    // Initialize result maps
    type BidAskData = {
      bid: number | null;
      ask: number | null;
      spread: number | null;
      spreadPercent: number | null;
      spreadCents: number | null;
    };
    let bidAskMap = new Map<string, BidAskData>();
    const statsMap = new Map<string, { volume24h: number; priceChange24h: number }>();

    // Run CLOB and ClickHouse queries in parallel
    const [clobResult, clickhouseResult] = await Promise.allSettled([
      // CLOB batch request
      (async () => {
        if (tokenIds.length === 0) return;
        try {
          const { getMultipleBidAsk } = await import('@/lib/polymarket/clob');
          const results = await getMultipleBidAsk(tokenIds);
          bidAskMap = results;
        } catch (error) {
          console.warn(
            '[markets/advanced] CLOB batch request failed:',
            error instanceof Error ? error.message : error
          );
        }
      })(),

      // ClickHouse stats query
      (async () => {
        if (marketIds.length === 0) return;
        try {
          const { queryClickHouse } = await import('@/lib/clickhouse');
          const clickhouseQuery = `
            SELECT
              market_id,
              sum(volume) as period_volume,
              argMin(avg_price, hour) as start_price,
              argMax(avg_price, hour) as end_price
            FROM market_stats_hourly
            WHERE hour >= now() - INTERVAL 24 HOUR
              AND market_id IN ({marketIds:Array(String)})
            GROUP BY market_id
          `;

          const statsRows = await queryClickHouse<{
            market_id: string;
            period_volume: string | number;
            start_price: string | number;
            end_price: string | number;
          }>(clickhouseQuery, { marketIds }, 5000);

          for (const row of statsRows) {
            const volume =
              typeof row.period_volume === 'string'
                ? parseFloat(row.period_volume)
                : row.period_volume;
            const startPrice =
              typeof row.start_price === 'string' ? parseFloat(row.start_price) : row.start_price;
            const endPrice =
              typeof row.end_price === 'string' ? parseFloat(row.end_price) : row.end_price;

            let priceChange = 0;
            if (startPrice > 0) {
              priceChange = ((endPrice - startPrice) / startPrice) * 100;
            }

            statsMap.set(row.market_id, {
              volume24h: volume || 0,
              priceChange24h: priceChange,
            });
          }
        } catch (error) {
          console.warn(
            '[markets/advanced] ClickHouse query failed (continuing without stats):',
            error instanceof Error ? error.message : error
          );
        }
      })(),
    ]);

    // Log any failures (for debugging)
    if (clobResult.status === 'rejected') {
      console.error('[markets/advanced] CLOB promise rejected:', clobResult.reason);
    }
    if (clickhouseResult.status === 'rejected') {
      console.error('[markets/advanced] ClickHouse promise rejected:', clickhouseResult.reason);
    }

    // Combine all data
    let combinedMarkets: AdvancedMarketData[] = markets.map((market) => {
      const tokenId = marketTokenMap.get(market.id);
      const bidAsk = tokenId ? bidAskMap.get(tokenId) : undefined;
      const stats = statsMap.get(market.polymarketId);

      // Fall back to last price if CLOB data not available
      const lastPrice = market.outcomes[0]?.currentPrice ?? null;

      return {
        id: market.id,
        polymarketId: market.polymarketId,
        conditionId: market.conditionId,
        slug: market.slug,
        question: market.question,
        description: market.description,
        category: market.category,
        endDate: market.endDate?.toISOString() ?? null,
        resolved: market.resolved,
        totalVolume: market.totalVolume,
        liquidity: market.liquidity,
        createdAt: market.createdAt.toISOString(),
        imageUrl: market.event?.imageUrl ?? null,
        outcomes: market.outcomes.map((o) => ({
          id: o.id,
          tokenId: o.tokenId,
          outcomeName: o.outcomeName,
          currentPrice: o.currentPrice,
          volume: o.volume,
        })),
        // CLOB bid/ask data (with fallback to last price)
        bid: bidAsk?.bid ?? lastPrice,
        ask: bidAsk?.ask ?? lastPrice,
        spread: bidAsk?.spread ?? 0,
        spreadPercent: bidAsk?.spreadPercent ?? 0,
        spreadCents: bidAsk?.spreadCents ?? 0,
        // 24h stats
        volume24h: stats?.volume24h ?? 0,
        priceChange24h: stats?.priceChange24h ?? 0,
      };
    });

    // For spread sorting, apply post-CLOB sorting and pagination
    if (!canSortAtDbLevel) {
      // Apply spread filters first
      if (minSpread !== null) {
        combinedMarkets = combinedMarkets.filter(
          (m) => m.spreadPercent !== null && m.spreadPercent >= minSpread
        );
      }
      if (maxSpread !== null) {
        combinedMarkets = combinedMarkets.filter(
          (m) => m.spreadPercent !== null && m.spreadPercent <= maxSpread
        );
      }
      if (minSpreadCents !== null) {
        combinedMarkets = combinedMarkets.filter(
          (m) => m.spreadCents !== null && m.spreadCents >= minSpreadCents
        );
      }
      if (maxSpreadCents !== null) {
        combinedMarkets = combinedMarkets.filter(
          (m) => m.spreadCents !== null && m.spreadCents <= maxSpreadCents
        );
      }

      // Sort by spread
      combinedMarkets.sort((a, b) => {
        const aValue = a.spreadPercent ?? (sortOrder === 'desc' ? -Infinity : Infinity);
        const bValue = b.spreadPercent ?? (sortOrder === 'desc' ? -Infinity : Infinity);
        return sortOrder === 'desc' ? bValue - aValue : aValue - bValue;
      });

      // Apply pagination for spread sorting
      combinedMarkets = combinedMarkets.slice(offset, offset + limit);
    }

    // Apply 24h change filters (for DB-level sorted results)
    if (canSortAtDbLevel) {
      if (minChange !== null) {
        combinedMarkets = combinedMarkets.filter((m) => m.priceChange24h >= minChange);
      }
      if (maxChange !== null) {
        combinedMarkets = combinedMarkets.filter((m) => m.priceChange24h <= maxChange);
      }
    }

    const totalPages = Math.ceil(total / limit);
    const currentPage = Math.floor(offset / limit) + 1;

    return NextResponse.json({
      markets: combinedMarkets,
      total,
      pagination: {
        limit,
        offset,
        page: currentPage,
        totalPages,
      },
    });
  } catch (error) {
    console.error('[markets/advanced] GET failed:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Failed to fetch advanced market data',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
