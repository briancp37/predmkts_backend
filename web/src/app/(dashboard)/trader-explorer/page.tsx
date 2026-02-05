/**
 * Trader Explorer Page
 *
 * PRD #13 (Sprint 4) - Create Trader Explorer page
 *
 * Features:
 * - Search input with Search icon
 * - Sort dropdown (Smart Score, Total PnL, Trade Count)
 * - Responsive card grid (2-3 columns)
 * - Trader cards with link to /analyze-user
 * - Loading skeleton cards
 */

'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Search, TrendingUp, TrendingDown, Activity, ChevronDown } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent } from '@/components/ui/card';
import { formatCurrency, formatPercent, shortenAddress, cn } from '@/lib/utils';

// Sort options for the dropdown
const SORT_OPTIONS = [
  { value: 'smartScore', label: 'Smart Score' },
  { value: 'totalPnl', label: 'Total PnL' },
  { value: 'totalTrades', label: 'Trade Count' },
] as const;

type SortValue = (typeof SORT_OPTIONS)[number]['value'];

// Trader type from API response
interface ExplorerTrader {
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
  winRate: number;
}

interface TradersResponse {
  traders: ExplorerTrader[];
  total: number;
  pagination: {
    limit: number;
    offset: number;
    hasMore: boolean;
  };
}

/**
 * Get score label based on score value
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
 * Get score color class based on score value
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

/**
 * Loading skeleton card component
 */
function SkeletonCard() {
  return (
    <Card className="animate-pulse">
      <CardContent className="pt-6">
        {/* Address skeleton */}
        <div className="h-5 w-32 rounded bg-gray-200" />
        {/* Username skeleton */}
        <div className="mt-1 h-4 w-24 rounded bg-gray-100" />
        {/* Score skeleton */}
        <div className="mt-4 flex items-baseline gap-2">
          <div className="h-8 w-16 rounded bg-gray-200" />
          <div className="h-4 w-12 rounded bg-gray-100" />
        </div>
        {/* Stats row skeleton */}
        <div className="mt-4 flex items-center justify-between">
          <div className="h-4 w-16 rounded bg-gray-100" />
          <div className="h-4 w-12 rounded bg-gray-100" />
          <div className="h-4 w-14 rounded bg-gray-100" />
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Trader card component
 */
function TraderCard({ trader }: { trader: ExplorerTrader }) {
  return (
    <Link href={`/analyze-user?address=${trader.address}`}>
      <Card className="transition-shadow hover:shadow-md">
        <CardContent className="pt-6">
          {/* Address and username */}
          <div className="font-mono text-sm font-medium text-gray-900">
            {shortenAddress(trader.address)}
          </div>
          {trader.username && <div className="text-sm text-gray-500">@{trader.username}</div>}

          {/* Smart Score */}
          <div className="mt-4 flex items-baseline gap-2">
            <span className={cn('text-2xl font-bold', getScoreColorClass(trader.smartScore))}>
              {trader.smartScore !== null ? trader.smartScore.toFixed(1) : 'N/A'}
            </span>
            <span className={cn('text-sm', getScoreColorClass(trader.smartScore))}>
              {getScoreLabel(trader.smartScore)}
            </span>
          </div>

          {/* Stats row */}
          <div className="mt-4 flex items-center justify-between text-sm">
            {/* PnL */}
            <div className="flex items-center gap-1">
              {trader.totalPnl >= 0 ? (
                <TrendingUp className="h-4 w-4 text-green-500" />
              ) : (
                <TrendingDown className="h-4 w-4 text-red-500" />
              )}
              <span
                className={cn(
                  'font-medium',
                  trader.totalPnl >= 0 ? 'text-green-600' : 'text-red-600'
                )}
              >
                {formatCurrency(trader.totalPnl)}
              </span>
            </div>

            {/* Trades */}
            <div className="flex items-center gap-1 text-gray-600">
              <Activity className="h-4 w-4" />
              <span>{trader.totalTrades.toLocaleString()}</span>
            </div>

            {/* Win rate */}
            <div className="text-gray-600">{formatPercent(trader.winRate)}</div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function TraderExplorerPage() {
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<SortValue>('smartScore');
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Fetch traders from API
  const { data, isLoading } = useQuery<TradersResponse>({
    queryKey: ['traders', search, sortBy],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (search.trim()) {
        params.set('search', search.trim());
      }
      params.set('sortBy', sortBy);
      params.set('limit', '50');

      const response = await fetch(`/api/traders?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Failed to fetch traders');
      }
      return response.json();
    },
  });

  // Get current sort label
  const currentSortLabel = SORT_OPTIONS.find((opt) => opt.value === sortBy)?.label || 'Smart Score';

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Trader Explorer</h1>
        <p className="mt-1 text-gray-500">
          Discover and analyze traders by their performance metrics
        </p>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col gap-4 sm:flex-row">
            {/* Search Input */}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search by address..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white py-2.5 pl-10 pr-4 text-gray-900 placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {/* Sort Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                onBlur={() => setTimeout(() => setIsDropdownOpen(false), 150)}
                className="flex w-full items-center justify-between gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 hover:bg-gray-50 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 sm:w-44"
              >
                <span>{currentSortLabel}</span>
                <ChevronDown
                  className={cn(
                    'h-4 w-4 text-gray-500 transition-transform',
                    isDropdownOpen && 'rotate-180'
                  )}
                />
              </button>

              {/* Dropdown Menu */}
              {isDropdownOpen && (
                <div className="absolute right-0 z-10 mt-1 w-full rounded-lg border border-gray-200 bg-white py-1 shadow-lg sm:w-44">
                  {SORT_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => {
                        setSortBy(option.value);
                        setIsDropdownOpen(false);
                      }}
                      className={cn(
                        'w-full px-4 py-2 text-left text-sm hover:bg-gray-50',
                        sortBy === option.value ? 'bg-indigo-50 text-indigo-600' : 'text-gray-700'
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Traders Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {isLoading ? (
          // Loading skeletons
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : data?.traders && data.traders.length > 0 ? (
          // Trader cards
          data.traders.map((trader) => <TraderCard key={trader.id} trader={trader} />)
        ) : (
          // Empty state
          <div className="col-span-full">
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Search className="h-12 w-12 text-gray-300" />
                <p className="mt-4 text-lg font-medium text-gray-900">No traders found</p>
                <p className="mt-1 text-sm text-gray-500">
                  {search
                    ? 'Try adjusting your search criteria'
                    : 'No traders available at this time'}
                </p>
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      {/* Results count */}
      {data && !isLoading && data.traders.length > 0 && (
        <div className="text-center text-sm text-gray-500">
          Showing {data.traders.length} of {data.total} traders
        </div>
      )}
    </div>
  );
}
