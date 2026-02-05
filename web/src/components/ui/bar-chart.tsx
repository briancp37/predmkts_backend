'use client';

import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { cn } from '@/lib/utils';

export interface BarChartDataItem {
  name: string;
  [key: string]: string | number;
}

export interface BarConfig {
  dataKey: string;
  color?: string;
  label?: string;
}

export interface BarChartProps {
  data: BarChartDataItem[];
  bars: BarConfig[];
  height?: number;
  className?: string;
  showGrid?: boolean;
  showLegend?: boolean;
  showTooltip?: boolean;
  loading?: boolean;
  emptyMessage?: string;
  xAxisDataKey?: string;
  formatYAxis?: (value: number) => string;
}

const DEFAULT_COLORS = [
  '#6366f1', // indigo
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#06b6d4', // cyan
];

export function BarChart({
  data,
  bars,
  height = 300,
  className,
  showGrid = true,
  showLegend = false,
  showTooltip = true,
  loading = false,
  emptyMessage = 'No data available',
  xAxisDataKey = 'name',
  formatYAxis,
}: BarChartProps) {
  if (loading) {
    return (
      <div
        className={cn('flex items-center justify-center bg-gray-50 rounded-lg', className)}
        style={{ height }}
        data-testid="bar-chart-loading"
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
        data-testid="bar-chart-empty"
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={cn('w-full', className)} style={{ height }} data-testid="bar-chart">
      <ResponsiveContainer width="100%" height="100%">
        <RechartsBarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
          <XAxis
            dataKey={xAxisDataKey}
            tick={{ fill: '#6b7280', fontSize: 12 }}
            tickLine={{ stroke: '#e5e7eb' }}
            axisLine={{ stroke: '#e5e7eb' }}
          />
          <YAxis
            tick={{ fill: '#6b7280', fontSize: 12 }}
            tickLine={{ stroke: '#e5e7eb' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickFormatter={formatYAxis}
          />
          {showTooltip && (
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
            />
          )}
          {showLegend && <Legend wrapperStyle={{ paddingTop: 16 }} />}
          {bars.map((bar, index) => (
            <Bar
              key={bar.dataKey}
              dataKey={bar.dataKey}
              name={bar.label || bar.dataKey}
              fill={bar.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length]}
              radius={[4, 4, 0, 0]}
            />
          ))}
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  );
}
