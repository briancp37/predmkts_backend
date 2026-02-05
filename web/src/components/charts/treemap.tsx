'use client';

import { useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';

// Dynamically import Plotly to avoid SSR issues
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

/**
 * Market node data structure from the API
 */
interface MarketNodeData {
  name: string;
  value: number;
  color: number;
  market_id: string;
  slug: string | null;
}

/**
 * Category node data structure from the API
 */
interface CategoryNodeData {
  name: string;
  children: MarketNodeData[];
}

/**
 * Hierarchical data structure from the API
 */
export interface TreemapData {
  name: string;
  children: CategoryNodeData[];
}

export interface TreemapProps {
  data: TreemapData | null;
  sizeMetric: string;
  colorMetric: string;
  height?: number;
  className?: string;
  loading?: boolean;
  onBlockClick?: (marketId: string, slug: string | null) => void;
}

/**
 * Flattens hierarchical treemap data into Plotly format arrays
 */
function flattenTreemapData(data: TreemapData): {
  ids: string[];
  labels: string[];
  parents: string[];
  values: number[];
  colors: number[];
  customdata: (string | null)[][];
} {
  const ids: string[] = [];
  const labels: string[] = [];
  const parents: string[] = [];
  const values: number[] = [];
  const colors: number[] = [];
  const customdata: (string | null)[][] = [];

  // Add root node
  const rootId = 'root-markets';
  ids.push(rootId);
  labels.push(data.name);
  parents.push('');
  values.push(0); // Root value will be auto-calculated by Plotly
  colors.push(0);
  customdata.push([null, null]); // [market_id, slug]

  // Add category nodes and market nodes
  for (const category of data.children) {
    const categoryId = `category-${category.name}`;

    ids.push(categoryId);
    labels.push(category.name);
    parents.push(rootId);
    values.push(0); // Category value will be sum of children
    colors.push(0); // Categories don't have a color value
    customdata.push([null, null]);

    // Add market nodes under this category
    for (const market of category.children) {
      const marketId = `market-${market.market_id}`;

      ids.push(marketId);
      // Truncate long market names for display
      const displayName =
        market.name.length > 50 ? market.name.substring(0, 47) + '...' : market.name;
      labels.push(displayName);
      parents.push(categoryId);
      values.push(market.value);
      colors.push(market.color);
      customdata.push([market.market_id, market.slug]);
    }
  }

  return { ids, labels, parents, values, colors, customdata };
}

/**
 * Treemap chart component using Plotly.js
 *
 * PRD #12 - Create Treemap chart component using Plotly.js
 *
 * Features:
 * - Hierarchical visualization of markets grouped by category
 * - Size represents the selected size metric (volume, liquidity, trades)
 * - Color represents the selected color metric (priceChange, smartMoneyFlow)
 * - Click handler for navigation to market detail pages
 * - Responsive sizing
 * - Loading and empty state handling
 */
export function Treemap({
  data,
  sizeMetric,
  colorMetric,
  height = 600,
  className,
  loading = false,
  onBlockClick,
}: TreemapProps) {
  // Flatten hierarchical data for Plotly
  const plotData = useMemo(() => {
    if (!data || data.children.length === 0) return null;
    return flattenTreemapData(data);
  }, [data]);

  // Handle click events on treemap blocks
  const handleClick = useCallback(
    (event: Plotly.PlotMouseEvent) => {
      if (!onBlockClick) return;

      const point = event.points[0];
      if (!point || !point.customdata) return;

      // customdata is stored as an array [market_id, slug]
      const customData = point.customdata as unknown as [string | null, string | null];
      const [marketId, slug] = customData;

      // Only navigate for market nodes (not categories or root)
      if (marketId) {
        onBlockClick(marketId, slug);
      }
    },
    [onBlockClick]
  );

  if (loading) {
    return (
      <div
        className={cn('flex items-center justify-center bg-gray-50 rounded-lg', className)}
        style={{ height }}
        data-testid="treemap-loading"
      >
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (!plotData) {
    return (
      <div
        className={cn(
          'flex items-center justify-center bg-gray-50 rounded-lg text-gray-500',
          className
        )}
        style={{ height }}
        data-testid="treemap-empty"
      >
        No market data available
      </div>
    );
  }

  // Determine color bar title based on metric
  const colorBarTitle =
    colorMetric === 'smartMoneyFlow' ? 'Smart Money Flow (%)' : 'Price Change (%)';

  // Determine hover template based on metrics
  const sizeLabel =
    sizeMetric === 'volume' ? 'Volume' : sizeMetric === 'liquidity' ? 'Liquidity' : 'Trades';

  return (
    <div className={cn('w-full', className)} style={{ height }} data-testid="treemap">
      <Plot
        data={[
          {
            type: 'treemap',
            ids: plotData.ids,
            labels: plotData.labels,
            parents: plotData.parents,
            values: plotData.values,
            customdata: plotData.customdata,
            marker: {
              colors: plotData.colors,
              colorscale: 'RdYlGn',
              cmid: 0, // Center the colorscale at 0
              colorbar: {
                title: {
                  text: colorBarTitle,
                  side: 'right',
                },
                thickness: 15,
                len: 0.8,
              },
              line: {
                width: 1,
                color: 'white',
              },
            },
            textposition: 'middle center',
            textfont: {
              size: 12,
              color: 'white',
            },
            hovertemplate:
              '<b>%{label}</b><br>' +
              `${sizeLabel}: %{value:,.0f}<br>` +
              `${colorBarTitle.replace(' (%)', '')}: %{color:.2f}%<br>` +
              '<extra></extra>',
            branchvalues: 'total',
            pathbar: {
              visible: true,
              thickness: 20,
              textfont: {
                size: 12,
              },
            },
          } as Partial<Plotly.PlotData>,
        ]}
        layout={{
          margin: { l: 0, r: 0, t: 30, b: 0 },
          paper_bgcolor: 'transparent',
          plot_bgcolor: 'transparent',
          font: {
            family:
              'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
          },
        }}
        config={{
          displayModeBar: false,
          responsive: true,
        }}
        style={{ width: '100%', height: '100%' }}
        onClick={handleClick}
        useResizeHandler
      />
    </div>
  );
}
