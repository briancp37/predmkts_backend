'use client';

import { useRef, useEffect } from 'react';
import {
  createChart,
  IChartApi,
  AreaData,
  Time,
  ColorType,
  AreaSeries,
  ISeriesApi,
  SeriesMarker,
  createSeriesMarkers,
  ISeriesMarkersPluginApi,
} from 'lightweight-charts';
import { cn } from '@/lib/utils';

export interface PriceChartData {
  time: string | number; // ISO date string or Unix timestamp
  value: number;
}

export interface TradeMarker {
  time: string | number;
  side: 'BUY' | 'SELL';
  price: number;
}

export interface PriceChartProps {
  data: PriceChartData[];
  trades?: TradeMarker[];
  height?: number;
  className?: string;
  lineColor?: string;
  areaTopColor?: string;
  areaBottomColor?: string;
  loading?: boolean;
  emptyMessage?: string;
}

export function PriceChart({
  data,
  trades,
  height = 300,
  className,
  lineColor = '#6366f1',
  areaTopColor = 'rgba(99, 102, 241, 0.4)',
  areaBottomColor = 'rgba(99, 102, 241, 0)',
  loading = false,
  emptyMessage = 'No data available',
}: PriceChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#6b7280',
      },
      grid: {
        vertLines: { color: '#e5e7eb' },
        horzLines: { color: '#e5e7eb' },
      },
      rightPriceScale: {
        borderColor: '#e5e7eb',
      },
      timeScale: {
        borderColor: '#e5e7eb',
        timeVisible: true,
      },
      crosshair: {
        vertLine: { labelBackgroundColor: '#6366f1' },
        horzLine: { labelBackgroundColor: '#6366f1' },
      },
    });

    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor,
      topColor: areaTopColor,
      bottomColor: areaBottomColor,
      lineWidth: 2,
    });

    // Create markers plugin for trade markers
    const seriesMarkers = createSeriesMarkers(areaSeries, []);

    chartRef.current = chart;
    seriesRef.current = areaSeries;
    markersRef.current = seriesMarkers;

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      if (markersRef.current) {
        markersRef.current.detach();
        markersRef.current = null;
      }
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height, lineColor, areaTopColor, areaBottomColor]);

  // Update data and markers
  useEffect(() => {
    if (!seriesRef.current || !data.length) return;

    const formattedData: AreaData<Time>[] = data.map((point) => ({
      time: (typeof point.time === 'number'
        ? point.time
        : new Date(point.time).getTime() / 1000) as Time,
      value: point.value,
    }));

    seriesRef.current.setData(formattedData);

    // Add trade markers if provided
    if (markersRef.current) {
      if (trades && trades.length > 0) {
        const markers: SeriesMarker<Time>[] = trades.map((trade) => ({
          time: (typeof trade.time === 'number'
            ? trade.time
            : new Date(trade.time).getTime() / 1000) as Time,
          position: trade.side === 'BUY' ? 'belowBar' : 'aboveBar',
          color: trade.side === 'BUY' ? '#22c55e' : '#ef4444',
          shape: trade.side === 'BUY' ? 'arrowUp' : 'arrowDown',
          text: trade.side,
        }));

        markersRef.current.setMarkers(markers);
      } else {
        markersRef.current.setMarkers([]);
      }
    }

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [data, trades]);

  if (loading) {
    return (
      <div
        className={cn('flex items-center justify-center bg-gray-50 rounded-lg', className)}
        style={{ height }}
        data-testid="price-chart-loading"
      >
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (!data.length) {
    return (
      <div
        className={cn(
          'flex items-center justify-center bg-gray-50 rounded-lg text-gray-500',
          className
        )}
        style={{ height }}
        data-testid="price-chart-empty"
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div ref={chartContainerRef} className={cn('w-full', className)} data-testid="price-chart" />
  );
}
