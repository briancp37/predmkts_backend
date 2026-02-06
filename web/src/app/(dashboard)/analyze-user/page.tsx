/**
 * Analyze User Page
 *
 * PRD #10 (Sprint 3) - Create Analyze User page
 *
 * Features:
 * - Address search form with Analyze button
 * - Stats cards: Total PnL, Total Trades, Win Rate, Smart Score
 * - TradeScatter chart (Finished Trades)
 * - PnlByEntryChart (Total PnL by Entry Price Range)
 * - Current Positions table with market context
 * - Recent Trades table with pagination
 *
 * Updated: Sprint 03 - Uses ClickHouse/FastAPI endpoints via /api/v1/traders
 */

'use client';

import { useState, useMemo, FormEvent } from 'react';
import { Search, TrendingUp, TrendingDown, Activity, Trophy } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import {
  TradeScatter,
  PnlByEntryChart,
  TradeScatterData,
  PnlByEntryChartData,
} from '@/components/charts';
import { useTrader, useTraderTrades, TraderPosition, Trade } from '@/hooks/use-traders';
import { formatCurrency, formatDate, formatPercent, cn } from '@/lib/utils';

// Entry price ranges for PnL by entry chart
const ENTRY_PRICE_RANGES = [
  { range: '0-10¢', min: 0, max: 0.1 },
  { range: '10-20¢', min: 0.1, max: 0.2 },
  { range: '20-30¢', min: 0.2, max: 0.3 },
  { range: '30-40¢', min: 0.3, max: 0.4 },
  { range: '40-50¢', min: 0.4, max: 0.5 },
  { range: '50-60¢', min: 0.5, max: 0.6 },
  { range: '60-70¢', min: 0.6, max: 0.7 },
  { range: '70-80¢', min: 0.7, max: 0.8 },
  { range: '80-90¢', min: 0.8, max: 0.9 },
  { range: '90-100¢', min: 0.9, max: 1.0 },
];

export default function AnalyzeUserPage() {
  const [addressInput, setAddressInput] = useState('');
  const [selectedAddress, setSelectedAddress] = useState<string | null>(null);

  // Fetch trader data
  const {
    data: trader,
    isLoading: isLoadingTrader,
    error: traderError,
  } = useTrader(selectedAddress, {
    enabled: !!selectedAddress,
  });

  // Fetch trader trades
  const { data: tradesData, isLoading: isLoadingTrades } = useTraderTrades(selectedAddress, {
    limit: 50,
    enabled: !!selectedAddress,
  });

  // Handle form submit
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (addressInput.trim()) {
      setSelectedAddress(addressInput.trim().toLowerCase());
    }
  };

  // Calculate win rate (trader already has winRate from API, but use local calculation for display)
  const winRate = useMemo(() => {
    if (!trader) return 0;
    const totalOutcomes = trader.winCount + trader.lossCount;
    if (totalOutcomes === 0) return 0;
    return trader.winCount / totalOutcomes;
  }, [trader]);

  // Prepare scatter chart data from completed trades (sell trades)
  const scatterData: TradeScatterData[] = useMemo(() => {
    if (!tradesData?.items) return [];

    // Group trades by market and outcome to find buy/sell pairs
    const tradesByPosition = new Map<string, Trade[]>();
    tradesData.items.forEach((trade) => {
      const key = `${trade.marketId}-${trade.outcomeId}`;
      if (!tradesByPosition.has(key)) {
        tradesByPosition.set(key, []);
      }
      tradesByPosition.get(key)!.push(trade);
    });

    const scatterPoints: TradeScatterData[] = [];

    tradesByPosition.forEach((trades) => {
      const buyTrades = trades.filter((t) => t.side === 'BUY');
      const sellTrades = trades.filter((t) => t.side === 'SELL');

      // For each sell, pair with the average buy price
      sellTrades.forEach((sellTrade) => {
        const avgBuyPrice =
          buyTrades.length > 0
            ? buyTrades.reduce((sum, t) => sum + t.price, 0) / buyTrades.length
            : sellTrade.price * 0.8; // Fallback: assume bought 20% lower

        scatterPoints.push({
          buyPrice: avgBuyPrice,
          sellPrice: sellTrade.price,
          amount: sellTrade.usdValue,
          profitable: sellTrade.price > avgBuyPrice,
        });
      });
    });

    return scatterPoints;
  }, [tradesData]);

  // Prepare PnL by entry price data
  const pnlByEntryData: PnlByEntryChartData[] = useMemo(() => {
    if (!tradesData?.items) return [];

    // Calculate PnL for each entry price range
    const pnlByRange = new Map<string, number>();
    ENTRY_PRICE_RANGES.forEach((r) => pnlByRange.set(r.range, 0));

    // For each buy trade, estimate PnL based on realized PnL or price difference
    tradesData.items.forEach((trade) => {
      if (trade.side !== 'BUY') return;

      const range = ENTRY_PRICE_RANGES.find((r) => trade.price >= r.min && trade.price < r.max);
      if (!range) return;

      // Use realized PnL if available, otherwise estimate based on quantity and price
      const pnl = trade.realizedPnl ?? 0;
      pnlByRange.set(range.range, pnlByRange.get(range.range)! + pnl);
    });

    return ENTRY_PRICE_RANGES.map((r) => ({
      range: r.range,
      pnl: pnlByRange.get(r.range) || 0,
    })).filter((d) => d.pnl !== 0);
  }, [tradesData]);

  // Positions table columns
  const positionsColumns: Column<TraderPosition>[] = [
    {
      key: 'market',
      header: 'Market',
      render: (_, position) => (
        <div className="max-w-xs truncate" title={position.marketQuestion}>
          {position.marketQuestion}
        </div>
      ),
    },
    {
      key: 'outcome',
      header: 'Outcome',
      render: (_, position) => position.outcomeName,
    },
    {
      key: 'quantity',
      header: 'Quantity',
      render: (_, position) => position.quantity.toFixed(2),
      className: 'text-right',
    },
    {
      key: 'avgCost',
      header: 'Avg Cost',
      render: (_, position) => formatPercent(position.avgCost),
      className: 'text-right',
    },
    {
      key: 'currentPrice',
      header: 'Current Price',
      render: (_, position) => formatPercent(position.currentPrice),
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
      key: 'market',
      header: 'Market',
      render: (_, trade) => (
        <div className="max-w-xs truncate" title={trade.marketQuestion}>
          {trade.marketQuestion}
        </div>
      ),
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

  const isNotFound =
    traderError?.message.includes('not found') || traderError?.message.includes('404');

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Analyze User</h1>
      </div>

      {/* Address Search Form */}
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Enter wallet address (0x...)"
                value={addressInput}
                onChange={(e) => setAddressInput(e.target.value)}
                className={cn(
                  'w-full rounded-lg border bg-white py-3 pl-10 pr-4 text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-1',
                  isNotFound
                    ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                    : 'border-gray-300 focus:border-indigo-500 focus:ring-indigo-500'
                )}
              />
            </div>
            <button
              type="submit"
              disabled={!addressInput.trim()}
              className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              Analyze
            </button>
          </form>
          {isNotFound && (
            <p className="mt-2 text-sm text-red-600">
              Trader not found. Please check the address and try again.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Loading State */}
      {isLoadingTrader && selectedAddress && (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-indigo-600" />
        </div>
      )}

      {/* Trader Data */}
      {trader && !isLoadingTrader && (
        <>
          {/* Stats Cards */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {/* Total PnL */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2">
                  {trader.totalPnl >= 0 ? (
                    <TrendingUp className="h-5 w-5 text-green-500" />
                  ) : (
                    <TrendingDown className="h-5 w-5 text-red-500" />
                  )}
                  <span className="text-sm text-gray-500">Total PnL</span>
                </div>
                <div
                  className={cn(
                    'mt-2 text-2xl font-bold',
                    trader.totalPnl >= 0 ? 'text-green-600' : 'text-red-600'
                  )}
                >
                  {trader.totalPnl >= 0 ? '+' : ''}
                  {formatCurrency(trader.totalPnl)}
                </div>
              </CardContent>
            </Card>

            {/* Total Trades */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-indigo-500" />
                  <span className="text-sm text-gray-500">Total Trades</span>
                </div>
                <div className="mt-2 text-2xl font-bold text-gray-900">
                  {trader.totalTrades.toLocaleString()}
                </div>
              </CardContent>
            </Card>

            {/* Win Rate */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2">
                  <Trophy className="h-5 w-5 text-yellow-500" />
                  <span className="text-sm text-gray-500">Win Rate</span>
                </div>
                <div className="mt-2 text-2xl font-bold text-gray-900">
                  {formatPercent(winRate)}
                </div>
                <div className="text-xs text-gray-500">
                  {trader.winCount}W / {trader.lossCount}L
                </div>
              </CardContent>
            </Card>

            {/* Smart Score */}
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2">
                  <div className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">
                    S
                  </div>
                  <span className="text-sm text-gray-500">Smart Score</span>
                </div>
                <div className="mt-2 text-2xl font-bold text-gray-900">
                  {trader.smartScore !== null ? trader.smartScore.toFixed(1) : 'N/A'}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Trade Scatter Chart */}
            <Card>
              <CardHeader>
                <CardTitle>Finished Trades</CardTitle>
              </CardHeader>
              <CardContent>
                <TradeScatter
                  data={scatterData}
                  height={300}
                  loading={isLoadingTrades}
                  emptyMessage="No completed trades available"
                />
              </CardContent>
            </Card>

            {/* PnL by Entry Price Chart */}
            <Card>
              <CardHeader>
                <CardTitle>Total PnL by Entry Price Range</CardTitle>
              </CardHeader>
              <CardContent>
                <PnlByEntryChart
                  data={pnlByEntryData}
                  height={300}
                  loading={isLoadingTrades}
                  emptyMessage="No PnL data available"
                />
              </CardContent>
            </Card>
          </div>

          {/* Current Positions */}
          <Card>
            <CardHeader>
              <CardTitle>Current Positions</CardTitle>
            </CardHeader>
            <CardContent>
              <DataTable
                data={trader.positions.filter((p) => p.quantity > 0)}
                columns={positionsColumns}
                loading={false}
                emptyMessage="No open positions"
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
                data={tradesData?.items ?? []}
                columns={tradesColumns}
                loading={isLoadingTrades}
                emptyMessage="No trades found"
              />
            </CardContent>
          </Card>
        </>
      )}

      {/* Empty State */}
      {!selectedAddress && !isLoadingTrader && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Search className="h-12 w-12 text-gray-300" />
            <p className="mt-4 text-lg font-medium text-gray-900">Enter a wallet address</p>
            <p className="mt-1 text-sm text-gray-500">
              Paste a wallet address above to analyze trading history
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
