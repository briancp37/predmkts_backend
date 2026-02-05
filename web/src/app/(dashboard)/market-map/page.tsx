/**
 * Market Map Page
 *
 * PRD #13 (Sprint 7) - Create Market Map page with treemap visualization
 *
 * Features:
 * - Interactive treemap visualization of market activity
 * - Time window selector: 6h, 12h, 24h, 7d
 * - Size metric selector: Volume, Liquidity, Trade Count
 * - Color metric selector: Price Change, Smart Money Flow
 * - Click handler for navigation to market detail pages
 * - Legend explaining size and color meanings
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Map, TrendingUp, TrendingDown, Info } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Treemap, TreemapData } from '@/components/charts';
import { cn } from '@/lib/utils';

// Time window options
const TIME_WINDOWS = ['6h', '12h', '24h', '7d'] as const;
type TimeWindow = (typeof TIME_WINDOWS)[number];

// Size metric options
const SIZE_METRICS = [
  { value: 'volume', label: 'Volume' },
  { value: 'liquidity', label: 'Liquidity' },
  { value: 'trades', label: 'Trade Count' },
] as const;
type SizeMetric = (typeof SIZE_METRICS)[number]['value'];

// Color metric options
const COLOR_METRICS = [
  { value: 'priceChange', label: 'Price Change' },
  { value: 'smartMoneyFlow', label: 'Smart Money Flow' },
] as const;
type ColorMetric = (typeof COLOR_METRICS)[number]['value'];

// API response type
interface MarketMapResponse {
  data: TreemapData;
  sizeMetric: string;
  colorMetric: string;
  timeWindow: string;
}

export default function MarketMapPage() {
  const router = useRouter();

  // State for controls
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('24h');
  const [sizeMetric, setSizeMetric] = useState<SizeMetric>('volume');
  const [colorMetric, setColorMetric] = useState<ColorMetric>('priceChange');

  // Fetch market map data
  const { data, isLoading, error, isFetching } = useQuery<MarketMapResponse>({
    queryKey: ['market-map', timeWindow, sizeMetric, colorMetric],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('timeWindow', timeWindow);
      params.set('sizeMetric', sizeMetric);
      params.set('colorMetric', colorMetric);

      const response = await fetch(`/api/markets/map?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Failed to fetch market map data');
      }
      return response.json();
    },
  });

  // Handle treemap block click to navigate to market detail
  const handleBlockClick = (marketId: string, slug: string | null) => {
    if (slug) {
      router.push(`/markets/${slug}`);
    } else {
      router.push(`/analyze-market?id=${marketId}`);
    }
  };

  // Get human-readable label for size metric
  const sizeMetricLabel = SIZE_METRICS.find((m) => m.value === sizeMetric)?.label ?? sizeMetric;

  // Get human-readable label for color metric
  const colorMetricLabel = COLOR_METRICS.find((m) => m.value === colorMetric)?.label ?? colorMetric;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <Map className="h-8 w-8 text-indigo-600" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Market Map</h1>
          <p className="text-gray-500">Interactive treemap visualization of market activity</p>
        </div>
      </div>

      {/* Controls Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Visualization Controls</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Time Window Selector */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">Time Window</label>
            <div className="flex flex-wrap gap-2">
              {TIME_WINDOWS.map((window) => (
                <button
                  key={window}
                  onClick={() => setTimeWindow(window)}
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
          </div>

          {/* Metric Selectors */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {/* Size Metric */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">Size Represents</label>
              <div className="space-y-1">
                {SIZE_METRICS.map((metric) => (
                  <label key={metric.value} className="flex cursor-pointer items-center gap-2">
                    <input
                      type="radio"
                      name="sizeMetric"
                      value={metric.value}
                      checked={sizeMetric === metric.value}
                      onChange={(e) => setSizeMetric(e.target.value as SizeMetric)}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-sm text-gray-700">{metric.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Color Metric */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">Color Represents</label>
              <div className="space-y-1">
                {COLOR_METRICS.map((metric) => (
                  <label key={metric.value} className="flex cursor-pointer items-center gap-2">
                    <input
                      type="radio"
                      name="colorMetric"
                      value={metric.value}
                      checked={colorMetric === metric.value}
                      onChange={(e) => setColorMetric(e.target.value as ColorMetric)}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-sm text-gray-700">{metric.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Treemap Visualization Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Market Treemap</CardTitle>
            {isFetching && !isLoading && <span className="text-sm text-gray-500">Updating...</span>}
          </div>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="flex h-[600px] items-center justify-center rounded-lg bg-red-50 text-red-600">
              <div className="text-center">
                <p className="font-medium">Failed to load market map</p>
                <p className="mt-1 text-sm">
                  {error instanceof Error ? error.message : 'Unknown error'}
                </p>
              </div>
            </div>
          ) : (
            <Treemap
              data={data?.data ?? null}
              sizeMetric={sizeMetric}
              colorMetric={colorMetric}
              height={600}
              loading={isLoading}
              onBlockClick={handleBlockClick}
            />
          )}
        </CardContent>
      </Card>

      {/* Legend Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-gray-500" />
            <CardTitle className="text-base">How to Read This Map</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {/* Size Legend */}
            <div className="space-y-2">
              <h4 className="font-medium text-gray-900">Block Size</h4>
              <p className="text-sm text-gray-600">
                The size of each block represents the market&apos;s{' '}
                <span className="font-medium text-indigo-600">{sizeMetricLabel}</span> over the
                selected time window. Larger blocks indicate more{' '}
                {sizeMetric === 'trades' ? 'trading activity' : sizeMetric}.
              </p>
            </div>

            {/* Color Legend */}
            <div className="space-y-2">
              <h4 className="font-medium text-gray-900">Block Color</h4>
              <p className="text-sm text-gray-600">
                The color of each block represents the market&apos;s{' '}
                <span className="font-medium text-indigo-600">{colorMetricLabel}</span>.
              </p>
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-1">
                  <div className="h-4 w-4 rounded bg-green-500" />
                  <span className="flex items-center gap-1 text-green-700">
                    <TrendingUp className="h-3 w-3" />
                    {colorMetric === 'priceChange' ? 'Price Up' : 'Net Buying'}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="h-4 w-4 rounded bg-yellow-400" />
                  <span className="text-yellow-700">Neutral</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="h-4 w-4 rounded bg-red-500" />
                  <span className="flex items-center gap-1 text-red-700">
                    <TrendingDown className="h-3 w-3" />
                    {colorMetric === 'priceChange' ? 'Price Down' : 'Net Selling'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Interaction Hint */}
          <div className="mt-4 rounded-lg bg-gray-50 p-3">
            <p className="text-sm text-gray-600">
              <span className="font-medium">Tip:</span> Click on any market block to view its
              detailed analysis page. Markets are grouped by category - click on a category to zoom
              in.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
