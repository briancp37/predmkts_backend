/**
 * Analyze Market Page
 *
 * PRD #9 (Sprint 3) - Create Analyze Market page
 *
 * Features:
 * - Market search with autocomplete
 * - Market header with category, question, total volume
 * - Outcomes grid showing outcome name and current price
 * - Price chart with TradingView Lightweight Charts
 * - Top positions table sorted by invested amount
 * - Recent trades table with trader, side, price, amount
 */

'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { PriceChart, PriceChartData, TradeMarker } from '@/components/charts';
import { useMarkets, useMarket, Market } from '@/hooks/use-markets';
import { formatCurrency, formatDate, formatPercent, shortenAddress, cn } from '@/lib/utils';

// Types for positions API response
interface PositionTrader {
  id: string;
  address: string;
  username: string | null;
  smartScore: number | null;
}

interface PositionOutcome {
  id: string;
  tokenId: string;
  outcomeName: string;
  currentPrice: number;
}

interface Position {
  id: string;
  quantity: number;
  avgPrice: number;
  investedUsd: number;
  currentValueUsd: number;
  realizedPnl: number;
  unrealizedPnl: number;
  trader: PositionTrader;
  outcome: PositionOutcome;
}

// Types for trades API response
interface Trade {
  id: string;
  timestamp: string;
  side: 'BUY' | 'SELL';
  price: number;
  amount: number;
  usdValue: number;
  trader: PositionTrader;
  outcome: PositionOutcome;
}

export default function AnalyzeMarketPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  // Fetch markets for autocomplete search
  const { data: searchData, isLoading: isSearching } = useMarkets({
    search: searchQuery,
    limit: 5,
    enabled: searchQuery.length > 2,
  });

  // Fetch selected market details
  const { data: market, isLoading: isLoadingMarket } = useMarket(selectedMarketId, {
    enabled: !!selectedMarketId,
  });

  // Fetch price history for selected market
  const { data: priceHistory, isLoading: isLoadingPriceHistory } = useQuery({
    queryKey: ['market-price-history', selectedMarketId],
    queryFn: async () => {
      const response = await fetch(`/api/markets/${selectedMarketId}/price-history`);
      if (!response.ok) throw new Error('Failed to fetch price history');
      return response.json() as Promise<PriceChartData[]>;
    },
    enabled: !!selectedMarketId,
  });

  // Fetch positions for selected market
  const { data: positionsData, isLoading: isLoadingPositions } = useQuery({
    queryKey: ['market-positions', selectedMarketId],
    queryFn: async () => {
      const response = await fetch(`/api/markets/${selectedMarketId}/positions?limit=10`);
      if (!response.ok) throw new Error('Failed to fetch positions');
      return response.json() as Promise<{ positions: Position[] }>;
    },
    enabled: !!selectedMarketId,
  });

  // Fetch trades for selected market
  const { data: tradesData, isLoading: isLoadingTrades } = useQuery({
    queryKey: ['market-trades', selectedMarketId],
    queryFn: async () => {
      const response = await fetch(`/api/markets/${selectedMarketId}/trades?limit=20`);
      if (!response.ok) throw new Error('Failed to fetch trades');
      return response.json() as Promise<{ trades: Trade[] }>;
    },
    enabled: !!selectedMarketId,
  });

  // Convert trades to price chart markers
  const tradeMarkers: TradeMarker[] = useMemo(() => {
    if (!tradesData?.trades) return [];
    return tradesData.trades.map((trade) => ({
      time: trade.timestamp,
      side: trade.side,
      price: trade.price,
    }));
  }, [tradesData]);

  // Handle market selection
  const handleSelectMarket = (market: Market) => {
    setSelectedMarketId(market.id);
    setSearchQuery('');
    setIsSearchFocused(false);
  };

  // Positions table columns
  const positionsColumns: Column<Position>[] = [
    {
      key: 'trader',
      header: 'Trader',
      render: (_, position) => (
        <div className="flex flex-col">
          <span className="font-medium">
            {position.trader.username || shortenAddress(position.trader.address)}
          </span>
          {position.trader.smartScore !== null && (
            <span className="text-xs text-gray-500">
              Score: {position.trader.smartScore.toFixed(1)}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'outcome',
      header: 'Outcome',
      render: (_, position) => position.outcome.outcomeName,
    },
    {
      key: 'investedUsd',
      header: 'Invested',
      render: (_, position) => formatCurrency(position.investedUsd),
      className: 'text-right',
    },
    {
      key: 'currentValueUsd',
      header: 'Current Value',
      render: (_, position) => formatCurrency(position.currentValueUsd),
      className: 'text-right',
    },
    {
      key: 'unrealizedPnl',
      header: 'Unrealized PnL',
      render: (_, position) => (
        <span
          className={cn(
            'font-medium',
            position.unrealizedPnl > 0
              ? 'text-green-600'
              : position.unrealizedPnl < 0
                ? 'text-red-600'
                : ''
          )}
        >
          {position.unrealizedPnl >= 0 ? '+' : ''}
          {formatCurrency(position.unrealizedPnl)}
        </span>
      ),
      className: 'text-right',
    },
  ];

  // Trades table columns
  const tradesColumns: Column<Trade>[] = [
    {
      key: 'timestamp',
      header: 'Time',
      render: (_, trade) => formatDate(trade.timestamp),
    },
    {
      key: 'trader',
      header: 'Trader',
      render: (_, trade) => trade.trader.username || shortenAddress(trade.trader.address),
    },
    {
      key: 'side',
      header: 'Side',
      render: (_, trade) => (
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2 py-1 text-xs font-medium',
            trade.side === 'BUY' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          )}
        >
          {trade.side}
        </span>
      ),
    },
    {
      key: 'price',
      header: 'Price',
      render: (_, trade) => formatPercent(trade.price),
      className: 'text-right',
    },
    {
      key: 'usdValue',
      header: 'Amount',
      render: (_, trade) => formatCurrency(trade.usdValue),
      className: 'text-right',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Analyze Market</h1>
      </div>

      {/* Search Input */}
      <Card>
        <CardContent className="pt-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search markets by question..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setIsSearchFocused(true)}
              onBlur={() => {
                // Delay to allow click on dropdown
                setTimeout(() => setIsSearchFocused(false), 200);
              }}
              className="w-full rounded-lg border border-gray-300 bg-white py-3 pl-10 pr-4 text-gray-900 placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />

            {/* Search Results Dropdown */}
            {isSearchFocused && searchQuery.length > 2 && (
              <div className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg">
                {isSearching ? (
                  <div className="flex items-center justify-center py-4">
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-indigo-600" />
                  </div>
                ) : searchData?.items.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-gray-500">No markets found</div>
                ) : (
                  searchData?.items.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => handleSelectMarket(m)}
                      className="w-full px-4 py-3 text-left hover:bg-gray-50 focus:bg-gray-50 focus:outline-none"
                    >
                      <div className="text-sm font-medium text-gray-900">{m.question}</div>
                      <div className="mt-0.5 flex items-center gap-2 text-xs text-gray-500">
                        {m.category && (
                          <span className="rounded bg-gray-100 px-1.5 py-0.5">{m.category}</span>
                        )}
                        <span>Vol: {formatCurrency(m.totalVolume)}</span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Selected Market Details */}
      {selectedMarketId && (
        <>
          {/* Market Header */}
          <Card>
            <CardHeader>
              {isLoadingMarket ? (
                <div className="h-6 w-48 animate-pulse rounded bg-gray-200" />
              ) : market?.category ? (
                <span className="inline-flex w-fit items-center rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700">
                  {market.category}
                </span>
              ) : null}
              <CardTitle className="text-xl">
                {isLoadingMarket ? (
                  <div className="h-7 w-full animate-pulse rounded bg-gray-200" />
                ) : (
                  market?.question
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-4">
                <div>
                  <span className="text-sm text-gray-500">Total Volume</span>
                  <div className="text-lg font-semibold">
                    {isLoadingMarket ? (
                      <div className="h-6 w-24 animate-pulse rounded bg-gray-200" />
                    ) : (
                      formatCurrency(market?.totalVolume ?? 0)
                    )}
                  </div>
                </div>
                {market?.endDate && (
                  <div>
                    <span className="text-sm text-gray-500">End Date</span>
                    <div className="text-lg font-semibold">
                      {formatDate(market.endDate, { relative: false })}
                    </div>
                  </div>
                )}
                {market?.resolved && (
                  <div>
                    <span className="text-sm text-gray-500">Status</span>
                    <div className="text-lg font-semibold text-green-600">Resolved</div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Outcomes Grid */}
          {market?.outcomes && market.outcomes.length > 0 && (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
              {market.outcomes.map((outcome) => (
                <Card key={outcome.id}>
                  <CardContent className="pt-4">
                    <div className="text-sm text-gray-500">{outcome.outcomeName}</div>
                    <div className="mt-1 text-2xl font-bold text-gray-900">
                      {formatPercent(outcome.currentPrice)}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Price Chart */}
          <Card>
            <CardHeader>
              <CardTitle>Price History</CardTitle>
            </CardHeader>
            <CardContent>
              <PriceChart
                data={priceHistory ?? []}
                trades={tradeMarkers}
                height={350}
                loading={isLoadingPriceHistory}
                emptyMessage="No price history available"
              />
            </CardContent>
          </Card>

          {/* Top Positions */}
          <Card>
            <CardHeader>
              <CardTitle>Top Positions</CardTitle>
            </CardHeader>
            <CardContent>
              <DataTable
                data={positionsData?.positions ?? []}
                columns={positionsColumns}
                loading={isLoadingPositions}
                emptyMessage="No positions found"
              />
            </CardContent>
          </Card>

          {/* Recent Trades */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Trades</CardTitle>
            </CardHeader>
            <CardContent>
              <DataTable
                data={tradesData?.trades ?? []}
                columns={tradesColumns}
                loading={isLoadingTrades}
                emptyMessage="No trades found"
              />
            </CardContent>
          </Card>
        </>
      )}

      {/* Empty State */}
      {!selectedMarketId && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Search className="h-12 w-12 text-gray-300" />
            <p className="mt-4 text-lg font-medium text-gray-900">Search for a market</p>
            <p className="mt-1 text-sm text-gray-500">
              Enter a market question above to view analytics
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
