/**
 * PnL Leaderboard Page
 *
 * PRD #14 (Sprint 7) - Create PnL Leaderboard page with period selector
 *
 * Features:
 * - Period selector: 1 Day, 7 Days, 30 Days, All Time
 * - DataTable with rank, trader address, smart score, PnL, trade count, win rate
 * - Medal emoji for top 3 (gold/silver/bronze)
 * - Conditional formatting for PnL (green/red)
 * - Smart score badge with emoji
 * - Win rate progress bar
 * - Update timestamp at bottom
 */

'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Trophy, TrendingUp, TrendingDown, Clock } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { formatCurrency, formatPercent, shortenAddress, cn } from '@/lib/utils';

// Period options for the leaderboard
const PERIODS = [
  { value: '1d', label: '1 Day' },
  { value: '7d', label: '7 Days' },
  { value: '30d', label: '30 Days' },
  { value: 'all', label: 'All Time' },
] as const;

type Period = (typeof PERIODS)[number]['value'];

// Leaderboard entry from API
interface LeaderboardEntry {
  trader_address: string;
  pnl: number;
  trade_count: number;
  win_rate: number;
  rank: number;
}

interface LeaderboardResponse {
  leaderboard: LeaderboardEntry[];
  period: string;
}

/**
 * Get medal emoji for top 3 ranks
 */
function getRankEmoji(rank: number): string {
  switch (rank) {
    case 1:
      return '🥇';
    case 2:
      return '🥈';
    case 3:
      return '🥉';
    default:
      return '';
  }
}

/**
 * Get background gradient class for top 3 rows
 */
function getTopRankBackground(rank: number): string {
  switch (rank) {
    case 1:
      return 'bg-gradient-to-r from-yellow-50 to-amber-50';
    case 2:
      return 'bg-gradient-to-r from-gray-50 to-slate-100';
    case 3:
      return 'bg-gradient-to-r from-orange-50 to-amber-50';
    default:
      return '';
  }
}

export default function PnlLeaderboardPage() {
  const [period, setPeriod] = useState<Period>('7d');

  // Fetch leaderboard data
  const { data, isLoading, dataUpdatedAt } = useQuery<LeaderboardResponse>({
    queryKey: ['leaderboard', period],
    queryFn: async () => {
      const response = await fetch(`/api/leaderboard?period=${period}&limit=100`);
      if (!response.ok) {
        throw new Error('Failed to fetch leaderboard');
      }
      return response.json();
    },
    refetchInterval: 60000, // Refresh every minute
  });

  // Table columns
  const columns: Column<LeaderboardEntry>[] = [
    {
      key: 'rank',
      header: 'Rank',
      render: (_, entry) => (
        <div
          className={cn('flex items-center gap-2 font-medium', getTopRankBackground(entry.rank))}
        >
          <span className="text-lg">{getRankEmoji(entry.rank)}</span>
          <span className={entry.rank <= 3 ? 'font-bold text-gray-900' : 'text-gray-700'}>
            #{entry.rank}
          </span>
        </div>
      ),
      className: 'w-24',
    },
    {
      key: 'trader_address',
      header: 'Trader',
      render: (_, entry) => (
        <Link
          href={`/analyze-user?address=${entry.trader_address}`}
          className="font-mono text-sm text-indigo-600 hover:text-indigo-800 hover:underline"
        >
          {shortenAddress(entry.trader_address)}
        </Link>
      ),
    },
    {
      key: 'pnl',
      header: 'PnL',
      render: (_, entry) => (
        <div className="flex items-center gap-1">
          {entry.pnl >= 0 ? (
            <TrendingUp className="h-4 w-4 text-green-500" />
          ) : (
            <TrendingDown className="h-4 w-4 text-red-500" />
          )}
          <span className={cn('font-bold', entry.pnl >= 0 ? 'text-green-600' : 'text-red-600')}>
            {entry.pnl >= 0 ? '+' : ''}
            {formatCurrency(entry.pnl)}
          </span>
        </div>
      ),
      className: 'text-right',
    },
    {
      key: 'trade_count',
      header: 'Trades',
      render: (_, entry) => (
        <span className="font-medium text-gray-700">{entry.trade_count.toLocaleString()}</span>
      ),
      className: 'text-right',
    },
    {
      key: 'win_rate',
      header: 'Win Rate',
      render: (_, entry) => {
        const winRatePercent = entry.win_rate * 100;
        return (
          <div className="flex items-center gap-2">
            {/* Progress bar */}
            <div className="h-2 w-20 overflow-hidden rounded-full bg-gray-200">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  winRatePercent >= 60
                    ? 'bg-green-500'
                    : winRatePercent >= 50
                      ? 'bg-yellow-500'
                      : 'bg-red-500'
                )}
                style={{ width: `${Math.min(winRatePercent, 100)}%` }}
              />
            </div>
            {/* Percentage text */}
            <span
              className={cn(
                'text-sm font-medium',
                winRatePercent >= 60
                  ? 'text-green-600'
                  : winRatePercent >= 50
                    ? 'text-yellow-600'
                    : 'text-red-600'
              )}
            >
              {formatPercent(entry.win_rate)}
            </span>
          </div>
        );
      },
      className: 'w-40',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <Trophy className="h-8 w-8 text-yellow-500" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">PnL Leaderboard</h1>
          <p className="text-gray-500">Top performing traders by profit and loss</p>
        </div>
      </div>

      {/* Period Selector Card */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-2 text-sm font-medium text-gray-700">Time Period:</span>
            {PERIODS.map((p) => (
              <button
                key={p.value}
                onClick={() => setPeriod(p.value)}
                className={cn(
                  'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                  period === p.value
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Leaderboard Table Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Trophy className="h-5 w-5 text-yellow-500" />
            Top Traders - {PERIODS.find((p) => p.value === period)?.label}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            data={data?.leaderboard ?? []}
            columns={columns}
            loading={isLoading}
            emptyMessage="No leaderboard data available for this period"
          />
        </CardContent>
      </Card>

      {/* Update Timestamp & Info */}
      {data && !isLoading && (
        <div className="space-y-2">
          {/* Update timestamp */}
          <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
            <Clock className="h-4 w-4" />
            <span>Updated {new Date(dataUpdatedAt).toLocaleString()}</span>
          </div>

          {/* Info callout */}
          <div className="rounded-lg bg-blue-50 p-4 text-center text-sm text-blue-700">
            <strong>Note:</strong> Leaderboard updates daily at midnight UTC
          </div>
        </div>
      )}
    </div>
  );
}
