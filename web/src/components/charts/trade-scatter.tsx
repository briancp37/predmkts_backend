'use client';

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
  Cell,
  ReferenceLine,
} from 'recharts';
import { cn, formatCurrency } from '@/lib/utils';

export interface TradeScatterData {
  buyPrice: number;
  sellPrice: number;
  amount: number;
  profitable: boolean;
}

export interface TradeScatterProps {
  data: TradeScatterData[];
  height?: number;
  className?: string;
  loading?: boolean;
  emptyMessage?: string;
}

const PROFITABLE_COLOR = '#22c55e';
const LOSS_COLOR = '#ef4444';

export function TradeScatter({
  data,
  height = 300,
  className,
  loading = false,
  emptyMessage = 'No trade data available',
}: TradeScatterProps) {
  if (loading) {
    return (
      <div
        className={cn('flex items-center justify-center bg-gray-50 rounded-lg', className)}
        style={{ height }}
        data-testid="trade-scatter-loading"
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
        data-testid="trade-scatter-empty"
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={cn('w-full', className)} style={{ height }} data-testid="trade-scatter">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            type="number"
            dataKey="buyPrice"
            name="Buy Price"
            domain={[0, 1]}
            tick={{ fill: '#6b7280', fontSize: 12 }}
            tickLine={{ stroke: '#e5e7eb' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickFormatter={(value: number) => `$${value.toFixed(2)}`}
            label={{ value: 'Buy Price', position: 'bottom', fill: '#6b7280', fontSize: 12 }}
          />
          <YAxis
            type="number"
            dataKey="sellPrice"
            name="Sell Price"
            domain={[0, 1]}
            tick={{ fill: '#6b7280', fontSize: 12 }}
            tickLine={{ stroke: '#e5e7eb' }}
            axisLine={{ stroke: '#e5e7eb' }}
            tickFormatter={(value: number) => `$${value.toFixed(2)}`}
            label={{
              value: 'Sell Price',
              angle: -90,
              position: 'insideLeft',
              fill: '#6b7280',
              fontSize: 12,
            }}
          />
          <ZAxis type="number" dataKey="amount" range={[50, 500]} name="Amount" />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            formatter={(value: number | undefined, name: string | undefined) => {
              if (value === undefined) return ['', undefined];
              if (name === 'Amount') {
                return [formatCurrency(value), name];
              }
              return [`$${value.toFixed(2)}`, name ?? ''];
            }}
            contentStyle={{
              backgroundColor: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: '6px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            }}
          />
          {/* Break-even line (diagonal where buy price = sell price) */}
          <ReferenceLine
            segment={[
              { x: 0, y: 0 },
              { x: 1, y: 1 },
            ]}
            stroke="#9ca3af"
            strokeDasharray="5 5"
            strokeWidth={1}
          />
          <Scatter name="Trades" data={data} fillOpacity={0.6}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.profitable ? PROFITABLE_COLOR : LOSS_COLOR} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
