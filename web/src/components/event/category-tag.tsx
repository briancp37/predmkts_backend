/**
 * Category Tag Component
 *
 * Sprint 02 - Market Display Components
 * PRD: category_tags
 *
 * Features:
 * - Create CategoryTag component with predefined color mapping
 * - Map categories to colors (Politics=blue, Crypto=orange, Tech=purple, etc.)
 * - Make tags clickable to navigate to category filter
 * - Add hover tooltip with full category name
 * - Support multiple tags per event
 */

'use client';

import { memo, useMemo } from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';

// ============================================================================
// Category Color Mapping
// ============================================================================

/**
 * Color configuration for a category
 */
export interface CategoryColors {
  bg: string;
  text: string;
  border: string;
  hoverBg: string;
}

/**
 * Full names for categories (used in tooltips)
 * Maps short category names to full descriptive names
 */
export const CATEGORY_FULL_NAMES: Record<string, string> = {
  Politics: 'Political Events & Elections',
  Crypto: 'Cryptocurrency & Blockchain',
  Tech: 'Technology & Innovation',
  Sports: 'Sports & Athletics',
  Entertainment: 'Entertainment & Media',
  Science: 'Science & Research',
  Economics: 'Economics & Markets',
  Finance: 'Financial Markets',
  World: 'World Events & News',
  Business: 'Business & Companies',
  Climate: 'Climate & Environment',
  Health: 'Health & Medicine',
  Legal: 'Legal & Regulatory',
  Culture: 'Culture & Society',
};

/**
 * Predefined color mapping for categories
 */
export const CATEGORY_COLORS: Record<string, CategoryColors> = {
  Politics: {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    hoverBg: 'hover:bg-blue-100',
  },
  Crypto: {
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    hoverBg: 'hover:bg-orange-100',
  },
  Tech: {
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    border: 'border-purple-200',
    hoverBg: 'hover:bg-purple-100',
  },
  Sports: {
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-green-200',
    hoverBg: 'hover:bg-green-100',
  },
  Entertainment: {
    bg: 'bg-pink-50',
    text: 'text-pink-700',
    border: 'border-pink-200',
    hoverBg: 'hover:bg-pink-100',
  },
  Science: {
    bg: 'bg-cyan-50',
    text: 'text-cyan-700',
    border: 'border-cyan-200',
    hoverBg: 'hover:bg-cyan-100',
  },
  Economics: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    hoverBg: 'hover:bg-emerald-100',
  },
  Finance: {
    bg: 'bg-yellow-50',
    text: 'text-yellow-700',
    border: 'border-yellow-200',
    hoverBg: 'hover:bg-yellow-100',
  },
  World: {
    bg: 'bg-indigo-50',
    text: 'text-indigo-700',
    border: 'border-indigo-200',
    hoverBg: 'hover:bg-indigo-100',
  },
  Business: {
    bg: 'bg-slate-50',
    text: 'text-slate-700',
    border: 'border-slate-200',
    hoverBg: 'hover:bg-slate-100',
  },
  Climate: {
    bg: 'bg-teal-50',
    text: 'text-teal-700',
    border: 'border-teal-200',
    hoverBg: 'hover:bg-teal-100',
  },
  Health: {
    bg: 'bg-rose-50',
    text: 'text-rose-700',
    border: 'border-rose-200',
    hoverBg: 'hover:bg-rose-100',
  },
  Legal: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    hoverBg: 'hover:bg-amber-100',
  },
  Culture: {
    bg: 'bg-fuchsia-50',
    text: 'text-fuchsia-700',
    border: 'border-fuchsia-200',
    hoverBg: 'hover:bg-fuchsia-100',
  },
};

const DEFAULT_CATEGORY_COLORS: CategoryColors = {
  bg: 'bg-gray-50',
  text: 'text-gray-700',
  border: 'border-gray-200',
  hoverBg: 'hover:bg-gray-100',
};

/**
 * Get color classes for a category
 * @param category - Category name (case-sensitive)
 * @returns Color configuration for the category
 */
export function getCategoryTagColors(category: string): CategoryColors {
  return CATEGORY_COLORS[category] || DEFAULT_CATEGORY_COLORS;
}

/**
 * Get the full name for a category (used in tooltips)
 * @param category - Category name
 * @returns Full descriptive name or the original category if no mapping exists
 */
export function getCategoryFullName(category: string): string {
  return CATEGORY_FULL_NAMES[category] || category;
}

// ============================================================================
// CategoryTag Component
// ============================================================================

export interface CategoryTagProps {
  /** Category name (e.g., "Politics", "Crypto") */
  category: string;
  /** Whether clicking navigates to category filter page */
  clickable?: boolean;
  /** Custom URL to navigate to (defaults to /markets?category={category}) */
  href?: string;
  /** Size variant */
  size?: 'sm' | 'md';
  /** Additional CSS classes */
  className?: string;
}

/**
 * Category tag with color coding, optional navigation, and tooltip.
 *
 * @example
 * ```tsx
 * // Non-clickable tag
 * <CategoryTag category="Crypto" />
 *
 * // Clickable tag that navigates to category filter
 * <CategoryTag category="Politics" clickable />
 *
 * // Custom navigation URL
 * <CategoryTag category="Tech" clickable href="/explore?cat=tech" />
 * ```
 */
export const CategoryTag = memo(function CategoryTag({
  category,
  clickable = false,
  href,
  size = 'md',
  className,
}: CategoryTagProps) {
  const colors = getCategoryTagColors(category);
  const fullName = getCategoryFullName(category);
  const defaultHref = `/markets?category=${encodeURIComponent(category.toLowerCase())}`;
  const navigationUrl = href ?? defaultHref;

  const sizeClasses = size === 'sm'
    ? 'px-2 py-0.5 text-xs'
    : 'px-2.5 py-0.5 text-xs';

  const baseClasses = cn(
    'inline-flex items-center rounded-full font-medium border transition-colors',
    sizeClasses,
    colors.bg,
    colors.text,
    colors.border,
    className
  );

  // Show full category name in tooltip
  const tooltipText = fullName !== category
    ? `${fullName} - Click to view all ${category} markets`
    : `Click to view all ${category} markets`;

  if (clickable) {
    return (
      <Link
        href={navigationUrl}
        className={cn(baseClasses, colors.hoverBg, 'cursor-pointer')}
        title={tooltipText}
        aria-label={`View ${category} markets`}
      >
        {category}
      </Link>
    );
  }

  return (
    <span
      className={baseClasses}
      title={fullName !== category ? fullName : undefined}
    >
      {category}
    </span>
  );
});

// ============================================================================
// CategoryTagList Component
// ============================================================================

export interface CategoryTagListProps {
  /** Array of category names */
  categories: string[];
  /** Whether tags are clickable (navigate to category filter) */
  clickable?: boolean;
  /** Size variant for all tags */
  size?: 'sm' | 'md';
  /** Maximum number of tags to show (rest shown as "+N more") */
  maxVisible?: number;
  /** Additional CSS classes for the container */
  className?: string;
}

/**
 * Renders a list of category tags with optional truncation.
 *
 * @example
 * ```tsx
 * // Show all tags
 * <CategoryTagList categories={['Politics', 'Crypto', 'Tech']} clickable />
 *
 * // Limit visible tags
 * <CategoryTagList categories={['A', 'B', 'C', 'D', 'E']} maxVisible={3} />
 * ```
 */
export const CategoryTagList = memo(function CategoryTagList({
  categories,
  clickable = false,
  size = 'md',
  maxVisible,
  className,
}: CategoryTagListProps) {
  const { visibleCategories, hiddenCount, hiddenCategories } = useMemo(() => {
    if (!maxVisible || categories.length <= maxVisible) {
      return {
        visibleCategories: categories,
        hiddenCount: 0,
        hiddenCategories: [] as string[],
      };
    }
    return {
      visibleCategories: categories.slice(0, maxVisible),
      hiddenCount: categories.length - maxVisible,
      hiddenCategories: categories.slice(maxVisible),
    };
  }, [categories, maxVisible]);

  if (categories.length === 0) {
    return null;
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {visibleCategories.map((category) => (
        <CategoryTag
          key={category}
          category={category}
          clickable={clickable}
          size={size}
        />
      ))}
      {hiddenCount > 0 && (
        <span
          className={cn(
            'inline-flex items-center rounded-full font-medium border',
            'bg-gray-50 text-gray-500 border-gray-200',
            size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-0.5 text-xs'
          )}
          title={`+${hiddenCount} more: ${hiddenCategories.join(', ')}`}
        >
          +{hiddenCount} more
        </span>
      )}
    </div>
  );
});
