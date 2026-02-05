'use client';

import * as React from 'react';
import {
  BarChart3,
  Droplets,
  Percent,
  DollarSign,
  ChevronDown,
  ChevronUp,
  Star,
  Tag,
  RotateCcw,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { MarketFilterCard } from './market-filter-card';
import type { MarketSortBy, SortOrder, TimeFilter } from '@/hooks/use-markets-advanced';

/**
 * Category options for the filter dropdown
 */
export const CATEGORY_OPTIONS = [
  { value: '', label: 'All Categories' },
  { value: 'Politics', label: 'Politics' },
  { value: 'Crypto', label: 'Crypto' },
  { value: 'Sports', label: 'Sports' },
  { value: 'Other', label: 'Other' },
] as const;

/**
 * Time filter options
 */
export const TIME_FILTER_OPTIONS: { value: TimeFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: '1d', label: '<1d' },
  { value: '7d', label: '<7d' },
  { value: '30d', label: '<30d' },
];

/**
 * Daily rewards filter options (in dollars)
 */
export const REWARDS_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'under20', label: '<$20' },
  { value: 'over20', label: '>$20' },
  { value: 'over100', label: '>$100' },
] as const;

/**
 * 24h change filter options
 */
export const CHANGE_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'under10', label: '<10%' },
  { value: 'over10', label: '>10%' },
  { value: 'over20', label: '>20%' },
] as const;

/**
 * All filter values that can be controlled by this component
 */
export interface MarketFilterValues {
  category: string;
  sortBy: MarketSortBy;
  sortOrder: SortOrder;
  minVolume: string;
  maxVolume: string;
  minLiquidity: string;
  maxLiquidity: string;
  minSpread: string;
  maxSpread: string;
  minSpreadCents: string;
  maxSpreadCents: string;
  timeRemaining: TimeFilter;
  createdDate: TimeFilter;
  rewards: string;
  change: string;
  tags: string[];
  watchlistOnly: boolean;
}

/**
 * Default filter values
 */
export const DEFAULT_FILTER_VALUES: MarketFilterValues = {
  category: '',
  sortBy: 'volume',
  sortOrder: 'desc',
  minVolume: '',
  maxVolume: '',
  minLiquidity: '',
  maxLiquidity: '',
  minSpread: '',
  maxSpread: '',
  minSpreadCents: '',
  maxSpreadCents: '',
  timeRemaining: 'all',
  createdDate: 'all',
  rewards: '',
  change: '',
  tags: [],
  watchlistOnly: false,
};

export interface MarketFiltersProps {
  /** Current filter values */
  values: MarketFilterValues;
  /** Callback when any filter value changes */
  onChange: (values: MarketFilterValues) => void;
  /** Callback when Tags button is clicked */
  onTagsClick?: () => void;
  /** Number of selected tags (for badge display) */
  selectedTagsCount?: number;
  /** Whether user is authenticated (for watchlist filter) */
  isAuthenticated?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Filter button component for time/rewards/change options
 */
function FilterButton({
  label,
  isActive,
  onClick,
}: {
  label: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        isActive
          ? 'bg-indigo-600 text-white'
          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
      )}
    >
      {label}
    </button>
  );
}

/**
 * Sort button component
 */
function SortButton({
  label,
  isActive,
  onClick,
}: {
  label: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
        isActive
          ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200'
          : 'bg-gray-50 text-gray-600 hover:bg-gray-100'
      )}
    >
      {label}
      {isActive && <Check className="h-3.5 w-3.5" />}
    </button>
  );
}

/**
 * MarketFilters component with all filter controls
 *
 * PRD #7 - Create MarketFilters component with all filter controls
 */
export function MarketFilters({
  values,
  onChange,
  onTagsClick,
  selectedTagsCount = 0,
  isAuthenticated = false,
  className,
}: MarketFiltersProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const [isCategoryOpen, setIsCategoryOpen] = React.useState(false);
  const categoryRef = React.useRef<HTMLDivElement>(null);

  // Handle outside click for category dropdown
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (categoryRef.current && !categoryRef.current.contains(event.target as Node)) {
        setIsCategoryOpen(false);
      }
    }
    if (isCategoryOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isCategoryOpen]);

  // Handle escape key for category dropdown
  React.useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsCategoryOpen(false);
      }
    }
    if (isCategoryOpen) {
      document.addEventListener('keydown', handleEscape);
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isCategoryOpen]);

  // Update a single filter value
  const updateFilter = <K extends keyof MarketFilterValues>(
    key: K,
    value: MarketFilterValues[K]
  ) => {
    onChange({ ...values, [key]: value });
  };

  // Handle sort button click
  const handleSortClick = (sortBy: MarketSortBy) => {
    if (values.sortBy === sortBy) {
      // Toggle sort order if same sort field
      updateFilter('sortOrder', values.sortOrder === 'desc' ? 'asc' : 'desc');
    } else {
      // New sort field, default to descending
      onChange({ ...values, sortBy, sortOrder: 'desc' });
    }
  };

  // Reset all filters to defaults
  const handleReset = () => {
    onChange(DEFAULT_FILTER_VALUES);
  };

  // Check if any filters are active (not default values)
  const hasActiveFilters =
    values.category !== '' ||
    values.minVolume !== '' ||
    values.maxVolume !== '' ||
    values.minLiquidity !== '' ||
    values.maxLiquidity !== '' ||
    values.minSpread !== '' ||
    values.maxSpread !== '' ||
    values.minSpreadCents !== '' ||
    values.maxSpreadCents !== '' ||
    values.timeRemaining !== 'all' ||
    values.createdDate !== 'all' ||
    values.rewards !== '' ||
    values.change !== '' ||
    values.tags.length > 0 ||
    values.watchlistOnly;

  const selectedCategory = CATEGORY_OPTIONS.find((opt) => opt.value === values.category);

  return (
    <div className={cn('space-y-4', className)}>
      {/* Top Row: Category dropdown + Sort buttons */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Category Dropdown */}
        <div ref={categoryRef} className="relative">
          <button
            type="button"
            onClick={() => setIsCategoryOpen(!isCategoryOpen)}
            className={cn(
              'flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors',
              values.category
                ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
                : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
            )}
            aria-expanded={isCategoryOpen}
            aria-haspopup="true"
          >
            {selectedCategory?.label || 'All Categories'}
            <ChevronDown
              className={cn(
                'h-4 w-4 transition-transform',
                isCategoryOpen && 'rotate-180'
              )}
            />
          </button>

          {isCategoryOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 min-w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
              {CATEGORY_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    updateFilter('category', option.value);
                    setIsCategoryOpen(false);
                  }}
                  className={cn(
                    'flex w-full items-center justify-between px-4 py-2 text-sm transition-colors',
                    values.category === option.value
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-gray-700 hover:bg-gray-50'
                  )}
                >
                  {option.label}
                  {values.category === option.value && (
                    <Check className="h-4 w-4" />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Sort Buttons */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">Sort by:</span>
          <SortButton
            label="Volume"
            isActive={values.sortBy === 'volume'}
            onClick={() => handleSortClick('volume')}
          />
          <SortButton
            label="Liquidity"
            isActive={values.sortBy === 'liquidity'}
            onClick={() => handleSortClick('liquidity')}
          />
          <SortButton
            label="Spread"
            isActive={values.sortBy === 'spread'}
            onClick={() => handleSortClick('spread')}
          />
        </div>

        {/* Reset Button */}
        {hasActiveFilters && (
          <button
            type="button"
            onClick={handleReset}
            className="ml-auto flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
          >
            <RotateCcw className="h-4 w-4" />
            Reset Filters
          </button>
        )}
      </div>

      {/* Filter Cards Grid with gradient background */}
      <div className="rounded-xl bg-gradient-to-br from-gray-50 via-white to-indigo-50/30 p-4 border border-gray-100">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MarketFilterCard
          label="24h Volume"
          icon={BarChart3}
          color="purple"
          minValue={values.minVolume}
          maxValue={values.maxVolume}
          onMinChange={(v) => updateFilter('minVolume', v)}
          onMaxChange={(v) => updateFilter('maxVolume', v)}
          description="Filter markets by their total trading volume in the last 24 hours. Higher volume indicates more active markets."
          minPlaceholder="Min $"
          maxPlaceholder="Max $"
        />
        <MarketFilterCard
          label="Liquidity"
          icon={Droplets}
          color="blue"
          minValue={values.minLiquidity}
          maxValue={values.maxLiquidity}
          onMinChange={(v) => updateFilter('minLiquidity', v)}
          onMaxChange={(v) => updateFilter('maxLiquidity', v)}
          description="Filter by available liquidity. Higher liquidity means less slippage when trading large amounts."
          minPlaceholder="Min $"
          maxPlaceholder="Max $"
        />
        <MarketFilterCard
          label="Spread %"
          icon={Percent}
          color="yellow"
          minValue={values.minSpread}
          maxValue={values.maxSpread}
          onMinChange={(v) => updateFilter('minSpread', v)}
          onMaxChange={(v) => updateFilter('maxSpread', v)}
          description="The percentage difference between bid and ask prices. Lower spread means better pricing efficiency."
          minPlaceholder="Min %"
          maxPlaceholder="Max %"
        />
        <MarketFilterCard
          label="Spread (cents)"
          icon={DollarSign}
          color="green"
          minValue={values.minSpreadCents}
          maxValue={values.maxSpreadCents}
          onMinChange={(v) => updateFilter('minSpreadCents', v)}
          onMaxChange={(v) => updateFilter('maxSpreadCents', v)}
          description="The absolute spread in cents between bid and ask. Useful for comparing spreads across different price points."
          minPlaceholder="Min ¢"
          maxPlaceholder="Max ¢"
        />
        </div>
      </div>

      {/* Expandable More Section */}
      <div className="rounded-lg border border-gray-200 bg-gray-50/50">
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100"
          aria-expanded={isExpanded}
        >
          <span className="flex items-center gap-2">
            More Filters
            {(values.timeRemaining !== 'all' ||
              values.createdDate !== 'all' ||
              values.rewards !== '' ||
              values.change !== '' ||
              values.tags.length > 0 ||
              values.watchlistOnly) && (
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
                Active
              </span>
            )}
          </span>
          {isExpanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>

        {isExpanded && (
          <div className="space-y-4 border-t border-gray-200 px-4 py-4">
            {/* Time Remaining */}
            <div className="flex flex-wrap items-center gap-3">
              <span className="w-28 text-sm font-medium text-gray-600">Time Remaining:</span>
              <div className="flex flex-wrap gap-2">
                {TIME_FILTER_OPTIONS.map((option) => (
                  <FilterButton
                    key={option.value}
                    label={option.label}
                    isActive={values.timeRemaining === option.value}
                    onClick={() => updateFilter('timeRemaining', option.value)}
                  />
                ))}
              </div>
            </div>

            {/* Created Date */}
            <div className="flex flex-wrap items-center gap-3">
              <span className="w-28 text-sm font-medium text-gray-600">Created:</span>
              <div className="flex flex-wrap gap-2">
                {TIME_FILTER_OPTIONS.map((option) => (
                  <FilterButton
                    key={option.value}
                    label={option.label}
                    isActive={values.createdDate === option.value}
                    onClick={() => updateFilter('createdDate', option.value)}
                  />
                ))}
              </div>
            </div>

            {/* Daily Rewards */}
            <div className="flex flex-wrap items-center gap-3">
              <span className="w-28 text-sm font-medium text-gray-600">Daily Rewards:</span>
              <div className="flex flex-wrap gap-2">
                {REWARDS_OPTIONS.map((option) => (
                  <FilterButton
                    key={option.value}
                    label={option.label}
                    isActive={values.rewards === option.value}
                    onClick={() => updateFilter('rewards', option.value)}
                  />
                ))}
              </div>
            </div>

            {/* 24h Change */}
            <div className="flex flex-wrap items-center gap-3">
              <span className="w-28 text-sm font-medium text-gray-600">24h Change:</span>
              <div className="flex flex-wrap gap-2">
                {CHANGE_OPTIONS.map((option) => (
                  <FilterButton
                    key={option.value}
                    label={option.label}
                    isActive={values.change === option.value}
                    onClick={() => updateFilter('change', option.value)}
                  />
                ))}
              </div>
            </div>

            {/* Tags and Watchlist Row */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              {/* Tags Button */}
              <button
                type="button"
                onClick={onTagsClick}
                className={cn(
                  'flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors',
                  selectedTagsCount > 0
                    ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
                    : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                )}
              >
                <Tag className="h-4 w-4" />
                Tags
                {selectedTagsCount > 0 && (
                  <span className="rounded-full bg-indigo-600 px-1.5 py-0.5 text-xs font-medium text-white">
                    {selectedTagsCount}
                  </span>
                )}
              </button>

              {/* Watchlist Toggle */}
              {isAuthenticated && (
                <button
                  type="button"
                  onClick={() => updateFilter('watchlistOnly', !values.watchlistOnly)}
                  className={cn(
                    'flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors',
                    values.watchlistOnly
                      ? 'border-yellow-200 bg-yellow-50 text-yellow-700'
                      : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                  )}
                >
                  <Star
                    className={cn('h-4 w-4', values.watchlistOnly && 'fill-yellow-500')}
                  />
                  Watchlist
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default MarketFilters;
