'use client';

import { useRef, useEffect } from 'react';
import { createChart, IChartApi, AreaData, Time, ColorType, AreaSeries } from 'lightweight-charts';
import { cn } from '@/lib/utils';

export interface PriceChartData {
  time: string | number; // ISO date string or Unix timestamp
  value: number;
}

export interface PriceChartProps {
  data: PriceChartData[];
  height?: number;
  className?: string;
  lineColor?: string;
  areaTopColor?: string;
  areaBottomColor?: string;
  loading?: boolean;
  emptyMessage?: string;
}

interface AreaSeriesRef {
  setData: (data: AreaData<Time>[]) => void;
}

export function PriceChart({
  data,
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
  const seriesRef = useRef<AreaSeriesRef | null>(null);

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

    chartRef.current = chart;
    seriesRef.current = areaSeries;

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
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height, lineColor, areaTopColor, areaBottomColor]);

  // Update data
  useEffect(() => {
    if (!seriesRef.current || !data.length) return;

    const formattedData: AreaData<Time>[] = data.map((point) => ({
      time: (typeof point.time === 'number'
        ? point.time
        : new Date(point.time).getTime() / 1000) as Time,
      value: point.value,
    }));

    seriesRef.current.setData(formattedData);

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [data]);

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
