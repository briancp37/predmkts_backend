'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { cn, formatCurrency } from '@/lib/utils';

export interface PnlByEntryChartData {
  range: string;
  pnl: number;
}

export interface PnlByEntryChartProps {
  data: PnlByEntryChartData[];
  height?: number;
  className?: string;
  loading?: boolean;
  emptyMessage?: string;
}

const POSITIVE_COLOR = '#22c55e';
const NEGATIVE_COLOR = '#ef4444';

export function PnlByEntryChart({
  data,
  height = 300,
  className,
  loading = false,
  emptyMessage = 'No PnL data available',
}: PnlByEntryChartProps) {
  if (loading) {
    return (
      <div
        className={cn('flex items-center justify-center bg-gray-50 rounded-lg', className)}
        style={{ height }}
        data-testid="pnl-by-entry-chart-loading"
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
        data-testid="pnl-by-entry-chart-empty"
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={cn('w-full', className)} style={{ height }} data-testid="pnl-by-entry-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="range"
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
              value !== undefined ? [formatCurrency(value), 'PnL'] : ['', undefined]
            }
            labelFormatter={(label: string) => `Entry Price: ${label}`}
            contentStyle={{
              backgroundColor: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: '6px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            }}
          />
          <Bar dataKey="pnl" name="PnL">
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
