'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/loading-skeleton';

export interface Column<T> {
  key: keyof T | string;
  header: string;
  render?: (value: unknown, item: T) => React.ReactNode;
  className?: string;
}

export interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  loading?: boolean;
  emptyMessage?: string;
  className?: string;
  /** Number of skeleton rows to show when loading (default: 5) */
  skeletonRows?: number;
}

function getNestedValue(item: unknown, key: string): unknown {
  const keys = key.split('.');
  let value: unknown = item;
  for (const k of keys) {
    if (value === null || value === undefined) {
      return undefined;
    }
    value = (value as Record<string, unknown>)[k];
  }
  return value;
}

export function DataTable<T>({
  data,
  columns,
  loading = false,
  emptyMessage = 'No data available',
  className,
  skeletonRows = 5,
}: DataTableProps<T>) {
  if (loading) {
    return (
      <div className={cn('overflow-hidden rounded-lg border border-gray-200', className)}>
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((column) => (
                <th
                  key={String(column.key)}
                  className={cn(
                    'px-4 py-3 text-left text-sm font-medium text-gray-700',
                    column.className
                  )}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {Array.from({ length: skeletonRows }).map((_, rowIndex) => (
              <tr
                key={rowIndex}
                style={{ animationDelay: `${rowIndex * 50}ms` }}
              >
                {columns.map((column) => (
                  <td
                    key={String(column.key)}
                    className={cn('px-4 py-3', column.className)}
                  >
                    <Skeleton className="h-4 w-full max-w-[120px]" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={cn('overflow-hidden rounded-lg border border-gray-200', className)}>
      <table className="w-full">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((column) => (
              <th
                key={String(column.key)}
                className={cn(
                  'px-4 py-3 text-left text-sm font-medium text-gray-700',
                  column.className
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {data.map((item, rowIndex) => (
            <tr key={rowIndex} className="hover:bg-gray-50">
              {columns.map((column) => {
                const value = getNestedValue(item, String(column.key));
                const cellContent = column.render
                  ? column.render(value, item)
                  : value !== null && value !== undefined
                    ? String(value)
                    : '';

                return (
                  <td
                    key={String(column.key)}
                    className={cn('px-4 py-3 text-sm text-gray-900', column.className)}
                  >
                    {cellContent}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

DataTable.displayName = 'DataTable';
