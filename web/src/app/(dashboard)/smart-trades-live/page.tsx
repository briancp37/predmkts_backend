/**
 * Smart Trades Live Page
 *
 * PRD #12 (Sprint 4) - Create Smart Trades Live page
 *
 * Features:
 * - Real-time trades from smart traders (ClickHouse trades_recent)
 * - Auto-refresh toggle with configurable interval
 * - Sound notification when new trades appear
 * - Filter by min score and min amount
 */

'use client';

import { useState, useRef, useEffect } from 'react';
import { Activity, RefreshCw, Volume2, VolumeX } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { formatCurrency, formatPercent, shortenAddress, formatDate, cn } from '@/lib/utils';

// Trade type from API response
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

interface SmartTradesResponse {
  trades: SmartTrade[];
}

/**
 * Get emoji for score value
 */
function getScoreEmoji(score: number | null): string {
  if (score === null) return '❓';
  if (score >= 50) return '🏆';
  if (score >= 25) return '💪';
  if (score >= 10) return '👍';
  if (score >= 0) return '😐';
  if (score >= -25) return '👎';
  return '💀';
}

/**
 * Get color class for score value
 */
function getScoreColorClass(score: number | null): string {
  if (score === null) return 'text-gray-400';
  if (score >= 50) return 'text-green-600';
  if (score >= 25) return 'text-green-500';
  if (score >= 10) return 'text-blue-500';
  if (score >= 0) return 'text-gray-500';
  if (score >= -25) return 'text-orange-500';
  return 'text-red-500';
}

export default function SmartTradesLivePage() {
  const [minScore, setMinScore] = useState(5);
  const [minAmount, setMinAmount] = useState(100);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(false);

  // Refs for sound notification and tracking new trades
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastTradeIdRef = useRef<string | null>(null);

  // Fetch trades from /api/trades/smart
  const { data, isLoading, isFetching } = useQuery<SmartTradesResponse>({
    queryKey: ['smart-trades-live', minScore, minAmount],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('minScore', minScore.toString());
      params.set('minAmount', minAmount.toString());
      params.set('limit', '100');

      const response = await fetch(`/api/trades/smart?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Failed to fetch smart trades');
      }
      return response.json();
    },
    refetchInterval: autoRefresh ? 5000 : false, // 5 second refresh when enabled
  });

  // Play sound when new trade appears
  useEffect(() => {
    if (!data?.trades || data.trades.length === 0) return;

    const latestTradeId = data.trades[0]?.id;

    // If we have a previous trade ID and it's different from the latest
    if (lastTradeIdRef.current && latestTradeId && lastTradeIdRef.current !== latestTradeId) {
      // New trade detected
      if (soundEnabled && audioRef.current) {
        audioRef.current.play().catch(() => {
          // Ignore autoplay errors
        });
      }
    }

    // Update the ref to track the latest trade
    lastTradeIdRef.current = latestTradeId ?? null;
  }, [data?.trades, soundEnabled]);

  // Table columns
  const columns: Column<SmartTrade>[] = [
    {
      key: 'timestamp',
      header: 'Time',
      render: (_, trade) => <span className="text-gray-600">{formatDate(trade.timestamp)}</span>,
      className: 'w-32',
    },
    {
      key: 'trader',
      header: 'Trader',
      render: (_, trade) => (
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-indigo-600">
            {shortenAddress(trade.trader_address)}
          </span>
          <span
            className={cn(
              'flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
              getScoreColorClass(trade.smart_score),
              trade.smart_score !== null && trade.smart_score >= 25
                ? 'bg-green-50'
                : trade.smart_score !== null && trade.smart_score >= 10
                  ? 'bg-blue-50'
                  : trade.smart_score !== null && trade.smart_score >= 0
                    ? 'bg-gray-50'
                    : 'bg-orange-50'
            )}
          >
            {getScoreEmoji(trade.smart_score)}
            <span>{trade.smart_score?.toFixed(0) ?? 'N/A'}</span>
          </span>
        </div>
      ),
    },
    {
      key: 'market_question',
      header: 'Market',
      render: (_, trade) => (
        <span className="line-clamp-2 text-gray-900" title={trade.market_question}>
          {trade.market_question.length > 60
            ? `${trade.market_question.slice(0, 60)}...`
            : trade.market_question}
        </span>
      ),
    },
    {
      key: 'side',
      header: 'Side',
      render: (_, trade) => (
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2 py-1 text-xs font-medium',
            trade.side === 'BUY' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          )}
        >
          {trade.side}
        </span>
      ),
      className: 'w-20',
    },
    {
      key: 'outcome_name',
      header: 'Outcome',
      render: (_, trade) => <span className="text-gray-700">{trade.outcome_name}</span>,
    },
    {
      key: 'price',
      header: 'Price',
      render: (_, trade) => formatPercent(trade.price),
      className: 'text-right w-20',
    },
    {
      key: 'usd_value',
      header: 'Amount',
      render: (_, trade) => (
        <span className="font-medium text-gray-900">{formatCurrency(trade.usd_value)}</span>
      ),
      className: 'text-right w-24',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Hidden audio element for notification sound */}
      <audio ref={audioRef} src="/notification.mp3" preload="auto" />

      {/* Page Header */}
      <div className="flex items-center gap-3">
        <Activity className="h-8 w-8 text-indigo-600" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Smart Trades Live</h1>
          <p className="text-gray-500">Real-time trades from high-scoring traders</p>
        </div>
      </div>

      {/* Filters Card */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            {/* Min Score Input */}
            <div className="flex-1">
              <label htmlFor="minScore" className="block text-sm font-medium text-gray-700">
                Min Score
              </label>
              <input
                type="number"
                id="minScore"
                value={minScore}
                onChange={(e) => setMinScore(Math.max(-100, Math.min(100, Number(e.target.value))))}
                min={-100}
                max={100}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {/* Min Amount Input */}
            <div className="flex-1">
              <label htmlFor="minAmount" className="block text-sm font-medium text-gray-700">
                Min Amount (USD)
              </label>
              <input
                type="number"
                id="minAmount"
                value={minAmount}
                onChange={(e) => setMinAmount(Math.max(0, Number(e.target.value)))}
                min={0}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {/* Auto-Refresh Toggle */}
            <div>
              <button
                type="button"
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                  autoRefresh
                    ? 'bg-green-600 text-white hover:bg-green-700'
                    : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                )}
              >
                <RefreshCw className={cn('h-4 w-4', autoRefresh && isFetching && 'animate-spin')} />
                {autoRefresh ? 'Auto-Refresh On' : 'Auto-Refresh Off'}
              </button>
            </div>

            {/* Sound Toggle */}
            <div>
              <button
                type="button"
                onClick={() => setSoundEnabled(!soundEnabled)}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                  soundEnabled
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                    : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                )}
              >
                {soundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
                {soundEnabled ? 'Sound On' : 'Sound Off'}
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Trades Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Recent Smart Trades</CardTitle>
            {autoRefresh && (
              <span className="flex items-center gap-2 text-sm text-green-600">
                <span className="h-2 w-2 animate-pulse rounded-full bg-green-600" />
                Live
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <DataTable
            data={data?.trades ?? []}
            columns={columns}
            loading={isLoading}
            emptyMessage="No smart trades found with current filters"
          />
        </CardContent>
      </Card>

      {/* Results Count */}
      {data && !isLoading && data.trades.length > 0 && (
        <div className="text-center text-sm text-gray-500">Showing {data.trades.length} trades</div>
      )}
    </div>
  );
}
