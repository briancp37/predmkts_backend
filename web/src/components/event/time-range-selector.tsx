/**
 * Time Range Selector Component
 *
 * Sprint 04 - Data Visualization
 * PRD: chart_time_range_selector
 *
 * Features:
 * - Button group for selecting chart time range
 * - Options: 1H, 6H, 1D, 1W, 1M, ALL
 * - Maps display ranges to Polymarket API intervals
 * - Accent color for selected range
 * - URL query param persistence
 * - Loading indicator during range change
 */

'use client';

import * as React from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { type TimeseriesInterval } from '@/hooks';

/**
 * User-facing time range options
 */
export type TimeRange = '1H' | '6H' | '1D' | '1W' | '1M' | 'ALL';

/**
 * Mapping from user-facing range to API interval
 *
 * - 1H: Uses 1m interval for granular intraday data
 * - 6H: Uses 5m interval for 6-hour view
 * - 1D: Uses 15m interval for daily view
 * - 1W: Uses 1h interval for weekly view
 * - 1M: Uses 6h interval for monthly view
 * - ALL: Uses max interval for full history
 */
export const TIME_RANGE_TO_INTERVAL: Record<TimeRange, TimeseriesInterval> = {
  '1H': '1m',
  '6H': '5m',
  '1D': '15m',
  '1W': '1h',
  '1M': '6h',
  'ALL': 'max',
};

/**
 * Default interval for internal components when no range is selected
 */
export const DEFAULT_TIME_RANGE: TimeRange = '1D';

/**
 * URL query parameter name for persisting time range
 */
const TIME_RANGE_PARAM = 'range';

/**
 * All available time ranges in display order
 */
const TIME_RANGES: TimeRange[] = ['1H', '6H', '1D', '1W', '1M', 'ALL'];

export interface TimeRangeSelectorProps {
  /** Controlled value - if provided, component is controlled */
  value?: TimeRange;
  /** Callback when range changes */
  onChange?: (range: TimeRange) => void;
  /** Whether data is currently loading (shows subtle indicator) */
  isLoading?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Whether to persist selection in URL (default: true) */
  persistInUrl?: boolean;
}

/**
 * Parse time range from URL search params
 */
function parseTimeRangeFromUrl(searchParams: URLSearchParams): TimeRange | null {
  const param = searchParams.get(TIME_RANGE_PARAM);
  if (param && TIME_RANGES.includes(param as TimeRange)) {
    return param as TimeRange;
  }
  return null;
}

/**
 * TimeRangeSelector - Button group for selecting chart time range
 *
 * Can be used in controlled or uncontrolled mode:
 * - Controlled: Pass `value` and `onChange`
 * - Uncontrolled: Uses URL query param for state persistence
 *
 * @example
 * ```tsx
 * // Uncontrolled - persists in URL
 * <TimeRangeSelector />
 *
 * // Controlled - manages own state
 * const [range, setRange] = useState<TimeRange>('1D');
 * <TimeRangeSelector value={range} onChange={setRange} isLoading={isLoading} />
 *
 * // Get the interval for API calls
 * const interval = TIME_RANGE_TO_INTERVAL[range];
 * const { data } = useTimeseries(tokenId, { interval });
 * ```
 */
export function TimeRangeSelector({
  value,
  onChange,
  isLoading = false,
  className,
  persistInUrl = true,
}: TimeRangeSelectorProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Determine if controlled or uncontrolled
  const isControlled = value !== undefined;

  // For uncontrolled mode: read from URL or use default
  const urlRange = React.useMemo(
    () => parseTimeRangeFromUrl(searchParams),
    [searchParams]
  );

  // Current selected range
  const selectedRange = isControlled ? value : (urlRange ?? DEFAULT_TIME_RANGE);

  // Handle range selection
  const handleSelect = React.useCallback(
    (range: TimeRange) => {
      // Call onChange callback if provided
      onChange?.(range);

      // Update URL for uncontrolled mode
      if (!isControlled && persistInUrl) {
        const params = new URLSearchParams(searchParams.toString());

        if (range === DEFAULT_TIME_RANGE) {
          // Remove param if it's the default value
          params.delete(TIME_RANGE_PARAM);
        } else {
          params.set(TIME_RANGE_PARAM, range);
        }

        const queryString = params.toString();
        const newUrl = queryString ? `${pathname}?${queryString}` : pathname;
        router.replace(newUrl, { scroll: false });
      }
    },
    [isControlled, onChange, persistInUrl, pathname, router, searchParams]
  );

  return (
    <div
      className={cn(
        'inline-flex items-center rounded-lg border border-gray-200 bg-white p-1',
        className
      )}
      role="group"
      aria-label="Chart time range"
    >
      {TIME_RANGES.map((range) => {
        const isSelected = range === selectedRange;
        const isLoadingThis = isLoading && isSelected;

        return (
          <button
            key={range}
            type="button"
            onClick={() => handleSelect(range)}
            disabled={isLoadingThis}
            className={cn(
              'relative flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2',
              isSelected
                ? 'bg-indigo-100 text-indigo-700'
                : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
              isLoadingThis && 'cursor-wait'
            )}
            aria-pressed={isSelected}
            aria-label={`${range} time range`}
          >
            {/* Loading spinner overlay for selected button */}
            {isLoadingThis && (
              <Loader2 className="absolute h-3 w-3 animate-spin text-indigo-600" />
            )}
            <span className={cn(isLoadingThis && 'opacity-0')}>{range}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * Hook to get the current time range from URL
 *
 * Useful when TimeRangeSelector is uncontrolled but you need the value
 * elsewhere (e.g., for fetching data)
 *
 * @example
 * ```tsx
 * const range = useTimeRangeFromUrl();
 * const interval = TIME_RANGE_TO_INTERVAL[range];
 * const { data } = useTimeseries(tokenId, { interval });
 * ```
 */
export function useTimeRangeFromUrl(): TimeRange {
  const searchParams = useSearchParams();
  return parseTimeRangeFromUrl(searchParams) ?? DEFAULT_TIME_RANGE;
}

/**
 * Hook to get the API interval from URL time range
 *
 * Convenience hook that combines URL reading and interval mapping
 *
 * @example
 * ```tsx
 * const interval = useTimeseriesIntervalFromUrl();
 * const { data } = useTimeseries(tokenId, { interval });
 * ```
 */
export function useTimeseriesIntervalFromUrl(): TimeseriesInterval {
  const range = useTimeRangeFromUrl();
  return TIME_RANGE_TO_INTERVAL[range];
}

export default TimeRangeSelector;
