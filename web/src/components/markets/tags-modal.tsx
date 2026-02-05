'use client';

import * as React from 'react';
import { X, Search, SortAsc, TrendingUp, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTags, type Tag, type TagSortBy } from '@/hooks/use-tags';

export interface TagsModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when the modal should close */
  onClose: () => void;
  /** Currently selected tag slugs */
  selectedTags: string[];
  /** Callback when tags selection changes (on Apply) */
  onApply: (tags: string[]) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * TagsModal component for filtering markets by tags
 *
 * PRD #10 - Create TagsModal component for tag filtering
 *
 * Features:
 * - Modal/drawer that slides in from right
 * - Search input to filter tags
 * - Tags displayed as clickable chips with market count
 * - Multi-select support (toggle tags on/off)
 * - Clear All and Apply buttons
 * - Sort by popularity (default) or alphabetically
 */
export function TagsModal({
  isOpen,
  onClose,
  selectedTags,
  onApply,
  className,
}: TagsModalProps) {
  // Local state for pending selection (before Apply)
  const [pendingTags, setPendingTags] = React.useState<Set<string>>(
    new Set(selectedTags)
  );
  const [search, setSearch] = React.useState('');
  const [sortBy, setSortBy] = React.useState<TagSortBy>('popular');

  // Fetch tags from API
  const { data: tagsData, isLoading } = useTags({
    search: search || undefined,
    sort: sortBy,
    enabled: isOpen,
  });

  // Sync pending tags with selected tags when modal opens
  React.useEffect(() => {
    if (isOpen) {
      setPendingTags(new Set(selectedTags));
      setSearch('');
    }
  }, [isOpen, selectedTags]);

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

  // Toggle a tag in the pending selection
  const toggleTag = (tagSlug: string) => {
    const newTags = new Set(pendingTags);
    if (newTags.has(tagSlug)) {
      newTags.delete(tagSlug);
    } else {
      newTags.add(tagSlug);
    }
    setPendingTags(newTags);
  };

  // Clear all pending selections
  const handleClearAll = () => {
    setPendingTags(new Set());
  };

  // Apply pending selections and close
  const handleApply = () => {
    onApply(Array.from(pendingTags));
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
  const pendingCount = pendingTags.size;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="tags-modal-title"
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
          <h2 id="tags-modal-title" className="text-lg font-semibold text-gray-900">
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
                const isSelected = pendingTags.has(tag.slug);
                return (
                  <button
                    key={tag.id}
                    type="button"
                    onClick={() => toggleTag(tag.slug)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-all',
                      isSelected
                        ? 'border-indigo-200 bg-indigo-100 text-indigo-700'
                        : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50'
                    )}
                  >
                    {isSelected && <Check className="h-3.5 w-3.5" />}
                    <span>{tag.name}</span>
                    <span
                      className={cn(
                        'rounded-full px-1.5 py-0.5 text-xs',
                        isSelected
                          ? 'bg-indigo-200 text-indigo-800'
                          : 'bg-gray-100 text-gray-500'
                      )}
                    >
                      {tag.marketCount}
                    </span>
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
            disabled={pendingCount === 0}
            className={cn(
              'text-sm font-medium transition-colors',
              pendingCount > 0
                ? 'text-gray-600 hover:text-gray-900'
                : 'cursor-not-allowed text-gray-300'
            )}
          >
            Clear All
            {pendingCount > 0 && (
              <span className="ml-1 text-gray-400">({pendingCount})</span>
            )}
          </button>
          <button
            type="button"
            onClick={handleApply}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            Apply
            {pendingCount > 0 && ` (${pendingCount})`}
          </button>
        </div>
      </div>
    </div>
  );
}

export default TagsModal;
