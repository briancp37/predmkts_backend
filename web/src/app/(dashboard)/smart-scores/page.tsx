/**
 * Smart Scores Page
 *
 * PRD #11 (Sprint 4) - Create Smart Scores page
 *
 * Features:
 * - Score explanation card with 6-column grid showing emoji, label, range for each tier
 * - Filters card with minScore/maxScore inputs and trader select dropdown
 * - Traders table with rank, address, smart score (with emoji), PnL, trades, win rate
 * - Trader detail panel when trader is selected
 */

'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Brain, TrendingUp, TrendingDown, Activity, Trophy, User, ChevronDown } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { formatCurrency, formatPercent, shortenAddress, cn } from '@/lib/utils';

// Score tiers with emoji, label, and range
const SCORE_TIERS = [
  { emoji: '🏆', label: 'Elite', min: 50, max: 100, color: 'text-green-600 bg-green-50' },
  { emoji: '💪', label: 'Strong', min: 25, max: 49, color: 'text-green-500 bg-green-50' },
  { emoji: '👍', label: 'Good', min: 10, max: 24, color: 'text-blue-500 bg-blue-50' },
  { emoji: '😐', label: 'Neutral', min: 0, max: 9, color: 'text-gray-500 bg-gray-50' },
  { emoji: '👎', label: 'Weak', min: -25, max: -1, color: 'text-orange-500 bg-orange-50' },
  { emoji: '💀', label: 'Poor', min: -100, max: -26, color: 'text-red-500 bg-red-50' },
] as const;

// Trader type from API response
interface SmartScoreTrader {
  id: string;
  address: string;
  username: string | null;
  smartScore: number;
  totalPnl: number;
  realizedPnl: number;
  totalTrades: number;
  winCount: number;
  lossCount: number;
  firstSeen: string;
  rank: number;
  winRate: number;
}

interface SmartScoresResponse {
  traders: SmartScoreTrader[];
  total: number;
  pagination: {
    limit: number;
    offset: number;
    hasMore: boolean;
  };
}

interface TraderDetail {
  id: string;
  address: string;
  username: string | null;
  smartScore: number | null;
  totalPnl: number;
  realizedPnl: number;
  totalTrades: number;
  winCount: number;
  lossCount: number;
  firstSeen: string;
  positions: unknown[];
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
 * Get label for score value
 */
function getScoreLabel(score: number | null): string {
  if (score === null) return 'N/A';
  if (score >= 50) return 'Elite';
  if (score >= 25) return 'Strong';
  if (score >= 10) return 'Good';
  if (score >= 0) return 'Neutral';
  if (score >= -25) return 'Weak';
  return 'Poor';
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

export default function SmartScoresPage() {
  const [minScore, setMinScore] = useState(0);
  const [maxScore, setMaxScore] = useState(100);
  const [selectedTrader, setSelectedTrader] = useState<string | null>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Fetch traders from /api/traders/smart-scores
  const { data, isLoading } = useQuery<SmartScoresResponse>({
    queryKey: ['smart-scores', minScore, maxScore],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('minScore', minScore.toString());
      params.set('maxScore', maxScore.toString());
      params.set('limit', '50');

      const response = await fetch(`/api/traders/smart-scores?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Failed to fetch smart scores');
      }
      return response.json();
    },
  });

  // Fetch trader detail when selectedTrader is set
  const { data: traderDetail, isLoading: isLoadingDetail } = useQuery<TraderDetail>({
    queryKey: ['trader-detail', selectedTrader],
    queryFn: async () => {
      if (!selectedTrader) throw new Error('No trader selected');
      const response = await fetch(`/api/traders/${selectedTrader}`);
      if (!response.ok) {
        throw new Error('Failed to fetch trader');
      }
      return response.json();
    },
    enabled: !!selectedTrader,
  });

  // Table columns
  const columns: Column<SmartScoreTrader>[] = [
    {
      key: 'rank',
      header: 'Rank',
      render: (_, trader) => <span className="font-medium text-gray-900">#{trader.rank}</span>,
      className: 'w-16',
    },
    {
      key: 'address',
      header: 'Address',
      render: (_, trader) => (
        <button
          type="button"
          onClick={() => setSelectedTrader(trader.address)}
          className="font-mono text-sm text-indigo-600 hover:text-indigo-800 hover:underline"
        >
          {shortenAddress(trader.address)}
          {trader.username && <span className="ml-2 text-gray-500">@{trader.username}</span>}
        </button>
      ),
    },
    {
      key: 'smartScore',
      header: 'Smart Score',
      render: (_, trader) => (
        <div className="flex items-center gap-2">
          <span className="text-lg">{getScoreEmoji(trader.smartScore)}</span>
          <span className={cn('font-bold', getScoreColorClass(trader.smartScore))}>
            {trader.smartScore.toFixed(1)}
          </span>
          <span className={cn('text-sm', getScoreColorClass(trader.smartScore))}>
            {getScoreLabel(trader.smartScore)}
          </span>
        </div>
      ),
    },
    {
      key: 'totalPnl',
      header: 'Total PnL',
      render: (_, trader) => (
        <span
          className={cn('font-medium', trader.totalPnl >= 0 ? 'text-green-600' : 'text-red-600')}
        >
          {trader.totalPnl >= 0 ? '+' : ''}
          {formatCurrency(trader.totalPnl)}
        </span>
      ),
      className: 'text-right',
    },
    {
      key: 'totalTrades',
      header: 'Trades',
      render: (_, trader) => trader.totalTrades.toLocaleString(),
      className: 'text-right',
    },
    {
      key: 'winRate',
      header: 'Win Rate',
      render: (_, trader) => formatPercent(trader.winRate),
      className: 'text-right',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <Brain className="h-8 w-8 text-indigo-600" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Smart Scores</h1>
          <p className="text-gray-500">
            Algorithmic trader rankings based on profitability, consistency, conviction, and breadth
          </p>
        </div>
      </div>

      {/* Score Explanation Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Score Tiers</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {SCORE_TIERS.map((tier) => (
              <div
                key={tier.label}
                className={cn('flex flex-col items-center rounded-lg p-3', tier.color)}
              >
                <span className="text-2xl">{tier.emoji}</span>
                <span className="mt-1 font-medium">{tier.label}</span>
                <span className="text-xs text-gray-600">
                  {tier.min} to {tier.max}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

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

            {/* Max Score Input */}
            <div className="flex-1">
              <label htmlFor="maxScore" className="block text-sm font-medium text-gray-700">
                Max Score
              </label>
              <input
                type="number"
                id="maxScore"
                value={maxScore}
                onChange={(e) => setMaxScore(Math.max(-100, Math.min(100, Number(e.target.value))))}
                min={-100}
                max={100}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {/* Trader Select Dropdown */}
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700">Quick Select Trader</label>
              <div className="relative mt-1">
                <button
                  type="button"
                  onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                  onBlur={() => setTimeout(() => setIsDropdownOpen(false), 150)}
                  className="flex w-full items-center justify-between gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 hover:bg-gray-50 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <span className="truncate">
                    {selectedTrader ? shortenAddress(selectedTrader) : 'Select trader...'}
                  </span>
                  <ChevronDown
                    className={cn(
                      'h-4 w-4 flex-shrink-0 text-gray-500 transition-transform',
                      isDropdownOpen && 'rotate-180'
                    )}
                  />
                </button>

                {isDropdownOpen && data?.traders && (
                  <div className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedTrader(null);
                        setIsDropdownOpen(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm text-gray-500 hover:bg-gray-50"
                    >
                      Clear selection
                    </button>
                    {data.traders.map((trader) => (
                      <button
                        key={trader.id}
                        type="button"
                        onClick={() => {
                          setSelectedTrader(trader.address);
                          setIsDropdownOpen(false);
                        }}
                        className={cn(
                          'w-full px-4 py-2 text-left text-sm hover:bg-gray-50',
                          selectedTrader === trader.address
                            ? 'bg-indigo-50 text-indigo-600'
                            : 'text-gray-700'
                        )}
                      >
                        <span className="font-mono">{shortenAddress(trader.address)}</span>
                        <span className="ml-2 text-gray-400">
                          {getScoreEmoji(trader.smartScore)} {trader.smartScore.toFixed(1)}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Selected Trader Detail Panel */}
      {selectedTrader && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Trader Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoadingDetail ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-indigo-600" />
              </div>
            ) : traderDetail ? (
              <div className="space-y-4">
                {/* Trader Header */}
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-mono text-lg font-medium">
                      {shortenAddress(traderDetail.address)}
                    </div>
                    {traderDetail.username && (
                      <div className="text-gray-500">@{traderDetail.username}</div>
                    )}
                  </div>
                  <Link
                    href={`/analyze-user?address=${traderDetail.address}`}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                  >
                    Full Analysis
                  </Link>
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                  {/* Trades */}
                  <div className="rounded-lg bg-gray-50 p-4">
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <Activity className="h-4 w-4" />
                      Trades
                    </div>
                    <div className="mt-1 text-xl font-bold">
                      {traderDetail.totalTrades.toLocaleString()}
                    </div>
                  </div>

                  {/* Total PnL */}
                  <div className="rounded-lg bg-gray-50 p-4">
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      {traderDetail.totalPnl >= 0 ? (
                        <TrendingUp className="h-4 w-4 text-green-500" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-red-500" />
                      )}
                      Total PnL
                    </div>
                    <div
                      className={cn(
                        'mt-1 text-xl font-bold',
                        traderDetail.totalPnl >= 0 ? 'text-green-600' : 'text-red-600'
                      )}
                    >
                      {traderDetail.totalPnl >= 0 ? '+' : ''}
                      {formatCurrency(traderDetail.totalPnl)}
                    </div>
                  </div>

                  {/* Wins */}
                  <div className="rounded-lg bg-gray-50 p-4">
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <Trophy className="h-4 w-4 text-yellow-500" />
                      Wins
                    </div>
                    <div className="mt-1 text-xl font-bold text-green-600">
                      {traderDetail.winCount}
                    </div>
                  </div>

                  {/* Losses */}
                  <div className="rounded-lg bg-gray-50 p-4">
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <TrendingDown className="h-4 w-4 text-red-500" />
                      Losses
                    </div>
                    <div className="mt-1 text-xl font-bold text-red-600">
                      {traderDetail.lossCount}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* Traders Table */}
      <Card>
        <CardHeader>
          <CardTitle>Ranked Traders</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            data={data?.traders ?? []}
            columns={columns}
            loading={isLoading}
            emptyMessage="No traders found in this score range"
          />
        </CardContent>
      </Card>

      {/* Results Count */}
      {data && !isLoading && data.traders.length > 0 && (
        <div className="text-center text-sm text-gray-500">
          Showing {data.traders.length} of {data.total} traders
        </div>
      )}
    </div>
  );
}
