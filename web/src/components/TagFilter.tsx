'use client';

import * as React from 'react';
import { X, Search, SortAsc, TrendingUp, Plus, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTags, type Tag, type TagSortBy } from '@/hooks/use-tags';

/**
 * Selection state for a tag
 * - 'include': Tag is included (green) - markets WITH this tag
 * - 'exclude': Tag is excluded (red) - markets WITHOUT this tag
 * - null: Tag is not selected
 */
export type TagSelectionState = 'include' | 'exclude' | null;

/**
 * Tag filter selection result
 */
export interface TagFilterSelection {
  /** Tags to include (markets must have at least one of these) */
  includeTags: string[];
  /** Tags to exclude (markets must not have any of these) */
  excludeTags: string[];
}

export interface TagFilterProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when the modal should close */
  onClose: () => void;
  /** Currently included tag slugs */
  includeTags: string[];
  /** Currently excluded tag slugs */
  excludeTags: string[];
  /** Callback when tags selection changes (on Apply) */
  onApply: (selection: TagFilterSelection) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * TagFilter component for filtering markets by including or excluding tags
 *
 * Sprint 07 - Event Tags: Frontend Tag Filter Component
 *
 * Features:
 * - Modal/drawer that slides in from right
 * - Search input to filter tags
 * - Tags displayed as clickable chips with market count
 * - Three-state toggle: not selected → include (green) → exclude (red) → not selected
 * - Visual distinction: green for include, red for exclude
 * - Clear All and Apply buttons
 * - Sort by popularity (default) or alphabetically
 */
export function TagFilter({
  isOpen,
  onClose,
  includeTags,
  excludeTags,
  onApply,
  className,
}: TagFilterProps) {
  // Local state for pending selection (before Apply)
  // Map of tagSlug -> 'include' | 'exclude' | null
  const [pendingSelections, setPendingSelections] = React.useState<Map<string, TagSelectionState>>(
    () => {
      const map = new Map<string, TagSelectionState>();
      includeTags.forEach((tag) => map.set(tag, 'include'));
      excludeTags.forEach((tag) => map.set(tag, 'exclude'));
      return map;
    }
  );
  const [search, setSearch] = React.useState('');
  const [sortBy, setSortBy] = React.useState<TagSortBy>('popular');

  // Fetch tags from API
  const { data: tagsData, isLoading } = useTags({
    search: search || undefined,
    sort: sortBy,
    enabled: isOpen,
  });

  // Sync pending selections with props when modal opens
  React.useEffect(() => {
    if (isOpen) {
      const map = new Map<string, TagSelectionState>();
      includeTags.forEach((tag) => map.set(tag, 'include'));
      excludeTags.forEach((tag) => map.set(tag, 'exclude'));
      setPendingSelections(map);
      setSearch('');
    }
  }, [isOpen, includeTags, excludeTags]);

  // Handle escape key to close modal
  React.useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  // Cycle through selection states: null → include → exclude → null
  const cycleTagState = (tagSlug: string) => {
    const newSelections = new Map(pendingSelections);
    const currentState = newSelections.get(tagSlug) || null;

    let nextState: TagSelectionState;
    if (currentState === null) {
      nextState = 'include';
    } else if (currentState === 'include') {
      nextState = 'exclude';
    } else {
      nextState = null;
    }

    if (nextState === null) {
      newSelections.delete(tagSlug);
    } else {
      newSelections.set(tagSlug, nextState);
    }

    setPendingSelections(newSelections);
  };

  // Set a specific state for a tag
  const setTagState = (tagSlug: string, state: TagSelectionState) => {
    const newSelections = new Map(pendingSelections);
    if (state === null) {
      newSelections.delete(tagSlug);
    } else {
      newSelections.set(tagSlug, state);
    }
    setPendingSelections(newSelections);
  };

  // Clear all pending selections
  const handleClearAll = () => {
    setPendingSelections(new Map());
  };

  // Apply pending selections and close
  const handleApply = () => {
    const includeList: string[] = [];
    const excludeList: string[] = [];

    pendingSelections.forEach((state, tagSlug) => {
      if (state === 'include') {
        includeList.push(tagSlug);
      } else if (state === 'exclude') {
        excludeList.push(tagSlug);
      }
    });

    onApply({ includeTags: includeList, excludeTags: excludeList });
    onClose();
  };

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!isOpen) return null;

  const tags = tagsData?.tags ?? [];
  const includeCount = Array.from(pendingSelections.values()).filter((s) => s === 'include').length;
  const excludeCount = Array.from(pendingSelections.values()).filter((s) => s === 'exclude').length;
  const totalCount = includeCount + excludeCount;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="tag-filter-title"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 transition-opacity" />

      {/* Drawer panel - slides in from right */}
      <div
        className={cn(
          'relative flex h-full w-full max-w-md flex-col bg-white shadow-xl transition-transform',
          'animate-in slide-in-from-right duration-300',
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h2 id="tag-filter-title" className="text-lg font-semibold text-gray-900">
            Filter by Tags
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Instructions */}
        <div className="border-b border-gray-200 bg-gray-50 px-4 py-2">
          <p className="text-xs text-gray-500">
            Click once to <span className="font-medium text-emerald-600">include</span> (show markets with tag),
            twice to <span className="font-medium text-red-600">exclude</span> (hide markets with tag),
            third click to clear.
          </p>
        </div>

        {/* Search and Sort */}
        <div className="space-y-3 border-b border-gray-200 px-4 py-3">
          {/* Search Input */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search tags..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-gray-50 py-2 pl-9 pr-3 text-sm placeholder:text-gray-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </div>

          {/* Sort Toggle */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">Sort:</span>
            <div className="inline-flex rounded-md border border-gray-200 bg-white p-0.5">
              <button
                type="button"
                onClick={() => setSortBy('popular')}
                className={cn(
                  'flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors',
                  sortBy === 'popular'
                    ? 'bg-indigo-100 text-indigo-700'
                    : 'text-gray-600 hover:text-gray-900'
                )}
              >
                <TrendingUp className="h-3 w-3" />
                Popular
              </button>
              <button
                type="button"
                onClick={() => setSortBy('alphabetical')}
                className={cn(
                  'flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors',
                  sortBy === 'alphabetical'
                    ? 'bg-indigo-100 text-indigo-700'
                    : 'text-gray-600 hover:text-gray-900'
                )}
              >
                <SortAsc className="h-3 w-3" />
                A-Z
              </button>
            </div>
          </div>

          {/* Selection Summary */}
          {totalCount > 0 && (
            <div className="flex items-center gap-2 text-xs">
              {includeCount > 0 && (
                <span className="flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-700">
                  <Plus className="h-3 w-3" />
                  {includeCount} included
                </span>
              )}
              {excludeCount > 0 && (
                <span className="flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-red-700">
                  <Minus className="h-3 w-3" />
                  {excludeCount} excluded
                </span>
              )}
            </div>
          )}
        </div>

        {/* Tags List */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div
                  key={i}
                  className="h-10 animate-pulse rounded-lg bg-gray-100"
                />
              ))}
            </div>
          ) : tags.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <p className="text-sm text-gray-500">
                {search ? 'No tags match your search' : 'No tags available'}
              </p>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {tags.map((tag: Tag) => {
                const state = pendingSelections.get(tag.slug) || null;
                const isIncluded = state === 'include';
                const isExcluded = state === 'exclude';

                return (
                  <button
                    key={tag.id}
                    type="button"
                    onClick={() => cycleTagState(tag.slug)}
                    className={cn(
                      'group relative flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-all',
                      isIncluded
                        ? 'border-emerald-200 bg-emerald-100 text-emerald-700'
                        : isExcluded
                        ? 'border-red-200 bg-red-100 text-red-700'
                        : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50'
                    )}
                    title={
                      isIncluded
                        ? 'Included - Click to exclude'
                        : isExcluded
                        ? 'Excluded - Click to clear'
                        : 'Click to include'
                    }
                  >
                    {isIncluded && <Plus className="h-3.5 w-3.5" />}
                    {isExcluded && <Minus className="h-3.5 w-3.5" />}
                    <span>{tag.name}</span>
                    <span
                      className={cn(
                        'rounded-full px-1.5 py-0.5 text-xs',
                        isIncluded
                          ? 'bg-emerald-200 text-emerald-800'
                          : isExcluded
                          ? 'bg-red-200 text-red-800'
                          : 'bg-gray-100 text-gray-500'
                      )}
                    >
                      {tag.marketCount}
                    </span>

                    {/* Quick action buttons on hover */}
                    {(isIncluded || isExcluded) && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setTagState(tag.slug, null);
                        }}
                        className={cn(
                          'absolute -right-1 -top-1 hidden h-4 w-4 items-center justify-center rounded-full bg-gray-600 text-white group-hover:flex',
                          'hover:bg-gray-800'
                        )}
                        aria-label="Clear selection"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3">
          <button
            type="button"
            onClick={handleClearAll}
            disabled={totalCount === 0}
            className={cn(
              'text-sm font-medium transition-colors',
              totalCount > 0
                ? 'text-gray-600 hover:text-gray-900'
                : 'cursor-not-allowed text-gray-300'
            )}
          >
            Clear All
            {totalCount > 0 && (
              <span className="ml-1 text-gray-400">({totalCount})</span>
            )}
          </button>
          <button
            type="button"
            onClick={handleApply}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            Apply
            {totalCount > 0 && ` (${totalCount})`}
          </button>
        </div>
      </div>
    </div>
  );
}

export default TagFilter;
