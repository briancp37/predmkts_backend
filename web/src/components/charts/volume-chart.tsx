'use client';

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { cn, formatCurrency } from '@/lib/utils';

export interface VolumeChartData {
  date: string;
  volume: number;
  buyVolume: number;
  sellVolume: number;
}

export interface VolumeChartProps {
  data: VolumeChartData[];
  height?: number;
  className?: string;
  loading?: boolean;
  emptyMessage?: string;
}

export function VolumeChart({
  data,
  height = 300,
  className,
  loading = false,
  emptyMessage = 'No volume data available',
}: VolumeChartProps) {
  if (loading) {
    return (
      <div
        className={cn('flex items-center justify-center bg-gray-50 rounded-lg', className)}
        style={{ height }}
        data-testid="volume-chart-loading"
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
        data-testid="volume-chart-empty"
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={cn('w-full', className)} style={{ height }} data-testid="volume-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="date"
            tick={{ fill: '#6b7280', fontSize: 12 }}
            tickLine={{ stroke: '#e5e7eb' }}
            axisLine={{ stroke: '#e5e7eb' }}
          />
          <YAxis
            tick={{ fill: '#6b7280', fontSize: 12 }}
            tickLine={{ stroke: '#e5e7eb' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickFormatter={(value: number) => formatCurrency(value)}
          />
          <Tooltip
            formatter={(value: number | undefined) =>
              value !== undefined ? [formatCurrency(value), undefined] : ['', undefined]
            }
            labelFormatter={(label: string) => `Date: ${label}`}
            contentStyle={{
              backgroundColor: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: '6px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            }}
          />
          <Bar dataKey="buyVolume" stackId="volume" fill="#22c55e" name="Buy Volume" />
          <Bar dataKey="sellVolume" stackId="volume" fill="#ef4444" name="Sell Volume" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
