/**
 * Market Screener Page
 *
 * PRD #11 (Sprint 7) - Create Market Screener page with filters and results table
 *
 * Features:
 * - Time window selector: 6h, 12h, 24h, 7d
 * - Volume range filters: minVolume, maxVolume
 * - Price change range filters: minPriceChange, maxPriceChange
 * - Category filter dropdown
 * - Resolved status toggle
 * - Sort by: volume, priceChange, liquidity
 * - Sort order: asc, desc
 * - Pagination controls
 * - Results DataTable with market info
 */

'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  Filter,
  TrendingUp,
  TrendingDown,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { formatCurrency, formatDate, cn } from '@/lib/utils';

// Time window options
const TIME_WINDOWS = ['6h', '12h', '24h', '7d'] as const;
type TimeWindow = (typeof TIME_WINDOWS)[number];

// Sort options
const SORT_OPTIONS = [
  { value: 'volume', label: 'Volume' },
  { value: 'priceChange', label: 'Price Change' },
  { value: 'liquidity', label: 'Liquidity' },
] as const;

// Market type from API response
interface ScreenerMarket {
  id: string;
  polymarketId: string;
  slug: string;
  question: string;
  category: string | null;
  endDate: string | null;
  resolved: boolean;
  liquidity: number;
  volume: number;
  priceChange: number;
  startPrice: number;
  endPrice: number;
  tradeCount: number;
}

interface ScreenerResponse {
  markets: ScreenerMarket[];
  total: number;
  timeWindow: string;
  pagination: {
    limit: number;
    offset: number;
  };
}

export default function MarketScreenerPage() {
  // Filter state
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('24h');
  const [minVolume, setMinVolume] = useState<string>('');
  const [maxVolume, setMaxVolume] = useState<string>('');
  const [minPriceChange, setMinPriceChange] = useState<string>('');
  const [maxPriceChange, setMaxPriceChange] = useState<string>('');
  const [category, setCategory] = useState<string>('');
  const [showResolved, setShowResolved] = useState(false);

  // Sort state
  const [sortBy, setSortBy] = useState<'volume' | 'priceChange' | 'liquidity'>('volume');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [isSortDropdownOpen, setIsSortDropdownOpen] = useState(false);

  // Pagination state
  const [offset, setOffset] = useState(0);
  const limit = 50;

  // Fetch markets from /api/markets/screener
  const { data, isLoading, isFetching } = useQuery<ScreenerResponse>({
    queryKey: [
      'market-screener',
      timeWindow,
      minVolume,
      maxVolume,
      minPriceChange,
      maxPriceChange,
      category,
      showResolved,
      sortBy,
      sortOrder,
      offset,
    ],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('timeWindow', timeWindow);
      params.set('sortBy', sortBy);
      params.set('sortOrder', sortOrder);
      params.set('limit', limit.toString());
      params.set('offset', offset.toString());

      if (minVolume) params.set('minVolume', minVolume);
      if (maxVolume) params.set('maxVolume', maxVolume);
      if (minPriceChange) params.set('minPriceChange', minPriceChange);
      if (maxPriceChange) params.set('maxPriceChange', maxPriceChange);
      if (category) params.set('category', category);
      if (showResolved) params.set('resolved', 'true');

      const response = await fetch(`/api/markets/screener?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Failed to fetch screener data');
      }
      return response.json();
    },
  });

  // Reset pagination when filters change
  const handleFilterChange = () => {
    setOffset(0);
  };

  // Table columns
  const columns: Column<ScreenerMarket>[] = [
    {
      key: 'question',
      header: 'Market',
      render: (_, market) => (
        <div className="max-w-md">
          <Link
            href={`/markets/${market.slug}`}
            className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline"
          >
            <span className="line-clamp-2">{market.question}</span>
          </Link>
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      render: (_, market) => (
        <span className="inline-flex rounded-full bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700">
          {market.category ?? 'Other'}
        </span>
      ),
      className: 'w-28',
    },
    {
      key: 'volume',
      header: 'Volume',
      render: (_, market) => (
        <span className="font-medium text-gray-900">{formatCurrency(market.volume)}</span>
      ),
      className: 'text-right w-28',
    },
    {
      key: 'priceChange',
      header: 'Price Change',
      render: (_, market) => (
        <div className="flex items-center justify-end gap-1">
          {market.priceChange >= 0 ? (
            <TrendingUp className="h-4 w-4 text-green-500" />
          ) : (
            <TrendingDown className="h-4 w-4 text-red-500" />
          )}
          <span
            className={cn(
              'font-medium',
              market.priceChange >= 0 ? 'text-green-600' : 'text-red-600'
            )}
          >
            {market.priceChange >= 0 ? '+' : ''}
            {market.priceChange.toFixed(2)}%
          </span>
        </div>
      ),
      className: 'text-right w-32',
    },
    {
      key: 'liquidity',
      header: 'Liquidity',
      render: (_, market) => (
        <span className="text-gray-700">{formatCurrency(market.liquidity)}</span>
      ),
      className: 'text-right w-28',
    },
    {
      key: 'endDate',
      header: 'End Date',
      render: (_, market) => (
        <span className="text-gray-500 text-sm">
          {market.endDate ? formatDate(market.endDate) : 'N/A'}
        </span>
      ),
      className: 'text-right w-28',
    },
  ];

  // Pagination helpers
  const hasMore = data ? offset + limit < data.total : false;
  const hasPrevious = offset > 0;
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = data ? Math.ceil(data.total / limit) : 0;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <Filter className="h-8 w-8 text-indigo-600" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Market Screener</h1>
          <p className="text-gray-500">
            Filter and discover markets by volume, price change, and more
          </p>
        </div>
      </div>

      {/* Time Window Selector */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-gray-700">Time Window:</span>
            {TIME_WINDOWS.map((window) => (
              <button
                key={window}
                onClick={() => {
                  setTimeWindow(window);
                  handleFilterChange();
                }}
                className={cn(
                  'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                  timeWindow === window
                    ? 'bg-indigo-600 text-white'
                    : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                )}
              >
                {window}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Filters Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Volume Range */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">Volume Range (USD)</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={minVolume}
                  onChange={(e) => {
                    setMinVolume(e.target.value);
                    handleFilterChange();
                  }}
                  min={0}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <input
                  type="number"
                  placeholder="Max"
                  value={maxVolume}
                  onChange={(e) => {
                    setMaxVolume(e.target.value);
                    handleFilterChange();
                  }}
                  min={0}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            {/* Price Change Range */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">Price Change (%)</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={minPriceChange}
                  onChange={(e) => {
                    setMinPriceChange(e.target.value);
                    handleFilterChange();
                  }}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <input
                  type="number"
                  placeholder="Max"
                  value={maxPriceChange}
                  onChange={(e) => {
                    setMaxPriceChange(e.target.value);
                    handleFilterChange();
                  }}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            {/* Category Filter */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">Category</label>
              <input
                type="text"
                placeholder="e.g., Politics, Crypto"
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  handleFilterChange();
                }}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {/* Resolved Toggle */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">Status</label>
              <button
                type="button"
                onClick={() => {
                  setShowResolved(!showResolved);
                  handleFilterChange();
                }}
                className={cn(
                  'w-full rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                  showResolved
                    ? 'bg-indigo-600 text-white'
                    : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                )}
              >
                {showResolved ? 'Resolved Only' : 'Active Only'}
              </button>
            </div>
          </div>

          {/* Sort Options */}
          <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-gray-200 pt-4">
            {/* Sort By Dropdown */}
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-700">Sort by:</span>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setIsSortDropdownOpen(!isSortDropdownOpen)}
                  onBlur={() => setTimeout(() => setIsSortDropdownOpen(false), 150)}
                  className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm text-gray-900 hover:bg-gray-50 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <span>{SORT_OPTIONS.find((o) => o.value === sortBy)?.label}</span>
                  <ChevronDown
                    className={cn(
                      'h-4 w-4 text-gray-500 transition-transform',
                      isSortDropdownOpen && 'rotate-180'
                    )}
                  />
                </button>

                {isSortDropdownOpen && (
                  <div className="absolute z-10 mt-1 w-full rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                    {SORT_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => {
                          setSortBy(option.value);
                          setIsSortDropdownOpen(false);
                          handleFilterChange();
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

            {/* Sort Order Toggle */}
            <button
              type="button"
              onClick={() => {
                setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc');
                handleFilterChange();
              }}
              className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              {sortOrder === 'desc' ? (
                <>
                  <TrendingDown className="h-4 w-4" />
                  Descending
                </>
              ) : (
                <>
                  <TrendingUp className="h-4 w-4" />
                  Ascending
                </>
              )}
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Results Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>
              Markets
              {data && !isLoading && (
                <span className="ml-2 text-sm font-normal text-gray-500">
                  ({data.total} results)
                </span>
              )}
            </CardTitle>
            {isFetching && !isLoading && <span className="text-sm text-gray-500">Updating...</span>}
          </div>
        </CardHeader>
        <CardContent>
          <DataTable
            data={data?.markets ?? []}
            columns={columns}
            loading={isLoading}
            emptyMessage="No markets found with current filters"
          />
        </CardContent>
      </Card>

      {/* Pagination Controls */}
      {data && data.total > 0 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-500">
            Showing {offset + 1} - {Math.min(offset + limit, data.total)} of {data.total} markets
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={!hasPrevious}
              className={cn(
                'flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                hasPrevious
                  ? 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                  : 'cursor-not-allowed bg-gray-100 text-gray-400'
              )}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </button>
            <span className="text-sm text-gray-700">
              Page {currentPage} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setOffset(offset + limit)}
              disabled={!hasMore}
              className={cn(
                'flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                hasMore
                  ? 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                  : 'cursor-not-allowed bg-gray-100 text-gray-400'
              )}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
