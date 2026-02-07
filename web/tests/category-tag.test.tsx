/**
 * Tests for CategoryTag and CategoryTagList components
 *
 * Sprint 02 - Market Display Components
 * PRD: category_tags
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  CategoryTag,
  CategoryTagList,
  getCategoryTagColors,
  getCategoryFullName,
  CATEGORY_COLORS,
} from '@/components/event/category-tag';

// ============================================================================
// getCategoryTagColors Tests
// ============================================================================

describe('getCategoryTagColors', () => {
  it('returns correct colors for Politics category', () => {
    const colors = getCategoryTagColors('Politics');
    expect(colors.bg).toBe('bg-blue-50');
    expect(colors.text).toBe('text-blue-700');
    expect(colors.border).toBe('border-blue-200');
    expect(colors.hoverBg).toBe('hover:bg-blue-100');
  });

  it('returns correct colors for Crypto category', () => {
    const colors = getCategoryTagColors('Crypto');
    expect(colors.bg).toBe('bg-orange-50');
    expect(colors.text).toBe('text-orange-700');
  });

  it('returns correct colors for Tech category', () => {
    const colors = getCategoryTagColors('Tech');
    expect(colors.bg).toBe('bg-purple-50');
    expect(colors.text).toBe('text-purple-700');
  });

  it('returns correct colors for Sports category', () => {
    const colors = getCategoryTagColors('Sports');
    expect(colors.bg).toBe('bg-green-50');
    expect(colors.text).toBe('text-green-700');
  });

  it('returns correct colors for Entertainment category', () => {
    const colors = getCategoryTagColors('Entertainment');
    expect(colors.bg).toBe('bg-pink-50');
    expect(colors.text).toBe('text-pink-700');
  });

  it('returns correct colors for Science category', () => {
    const colors = getCategoryTagColors('Science');
    expect(colors.bg).toBe('bg-cyan-50');
    expect(colors.text).toBe('text-cyan-700');
  });

  it('returns correct colors for Economics category', () => {
    const colors = getCategoryTagColors('Economics');
    expect(colors.bg).toBe('bg-emerald-50');
    expect(colors.text).toBe('text-emerald-700');
  });

  it('returns correct colors for Finance category', () => {
    const colors = getCategoryTagColors('Finance');
    expect(colors.bg).toBe('bg-yellow-50');
    expect(colors.text).toBe('text-yellow-700');
  });

  it('returns correct colors for World category', () => {
    const colors = getCategoryTagColors('World');
    expect(colors.bg).toBe('bg-indigo-50');
    expect(colors.text).toBe('text-indigo-700');
  });

  it('returns correct colors for Business category', () => {
    const colors = getCategoryTagColors('Business');
    expect(colors.bg).toBe('bg-slate-50');
    expect(colors.text).toBe('text-slate-700');
  });

  it('returns correct colors for Climate category', () => {
    const colors = getCategoryTagColors('Climate');
    expect(colors.bg).toBe('bg-teal-50');
    expect(colors.text).toBe('text-teal-700');
  });

  it('returns correct colors for Health category', () => {
    const colors = getCategoryTagColors('Health');
    expect(colors.bg).toBe('bg-rose-50');
    expect(colors.text).toBe('text-rose-700');
  });

  it('returns default gray colors for unknown category', () => {
    const colors = getCategoryTagColors('UnknownCategory');
    expect(colors.bg).toBe('bg-gray-50');
    expect(colors.text).toBe('text-gray-700');
    expect(colors.border).toBe('border-gray-200');
    expect(colors.hoverBg).toBe('hover:bg-gray-100');
  });

  it('is case-sensitive', () => {
    const colors = getCategoryTagColors('politics');
    expect(colors.bg).toBe('bg-gray-50'); // Should be default since it's lowercase
  });
});

// ============================================================================
// getCategoryFullName Tests
// ============================================================================

describe('getCategoryFullName', () => {
  it('returns full name for Politics', () => {
    expect(getCategoryFullName('Politics')).toBe('Political Events & Elections');
  });

  it('returns full name for Crypto', () => {
    expect(getCategoryFullName('Crypto')).toBe('Cryptocurrency & Blockchain');
  });

  it('returns full name for Tech', () => {
    expect(getCategoryFullName('Tech')).toBe('Technology & Innovation');
  });

  it('returns full name for Sports', () => {
    expect(getCategoryFullName('Sports')).toBe('Sports & Athletics');
  });

  it('returns full name for Entertainment', () => {
    expect(getCategoryFullName('Entertainment')).toBe('Entertainment & Media');
  });

  it('returns full name for Science', () => {
    expect(getCategoryFullName('Science')).toBe('Science & Research');
  });

  it('returns the original category for unknown categories', () => {
    expect(getCategoryFullName('CustomCategory')).toBe('CustomCategory');
  });
});

// ============================================================================
// CATEGORY_COLORS Export Tests
// ============================================================================

describe('CATEGORY_COLORS', () => {
  it('contains all expected categories', () => {
    const expectedCategories = [
      'Politics', 'Crypto', 'Tech', 'Sports', 'Entertainment',
      'Science', 'Economics', 'Finance', 'World', 'Business',
      'Climate', 'Health', 'Legal', 'Culture'
    ];

    expectedCategories.forEach(category => {
      const colors = CATEGORY_COLORS[category];
      expect(colors).toBeDefined();
      expect(colors?.bg).toBeDefined();
      expect(colors?.text).toBeDefined();
      expect(colors?.border).toBeDefined();
      expect(colors?.hoverBg).toBeDefined();
    });
  });
});

// ============================================================================
// CategoryTag Component Tests
// ============================================================================

describe('CategoryTag', () => {
  describe('rendering', () => {
    it('renders category name', () => {
      render(<CategoryTag category="Politics" />);
      expect(screen.getByText('Politics')).toBeInTheDocument();
    });

    it('renders as span when not clickable', () => {
      render(<CategoryTag category="Crypto" />);
      const element = screen.getByText('Crypto');
      expect(element.tagName).toBe('SPAN');
    });

    it('renders as link when clickable', () => {
      render(<CategoryTag category="Tech" clickable />);
      const element = screen.getByRole('link');
      expect(element).toHaveTextContent('Tech');
    });

    it('applies correct color classes for known category', () => {
      render(<CategoryTag category="Politics" />);
      const element = screen.getByText('Politics');
      expect(element).toHaveClass('bg-blue-50');
      expect(element).toHaveClass('text-blue-700');
      expect(element).toHaveClass('border-blue-200');
    });

    it('applies default color classes for unknown category', () => {
      render(<CategoryTag category="Unknown" />);
      const element = screen.getByText('Unknown');
      expect(element).toHaveClass('bg-gray-50');
      expect(element).toHaveClass('text-gray-700');
      expect(element).toHaveClass('border-gray-200');
    });

    it('applies custom className', () => {
      render(<CategoryTag category="Crypto" className="custom-class" />);
      const element = screen.getByText('Crypto');
      expect(element).toHaveClass('custom-class');
    });
  });

  describe('size variants', () => {
    it('applies md size classes by default', () => {
      render(<CategoryTag category="Sports" />);
      const element = screen.getByText('Sports');
      expect(element).toHaveClass('px-2.5');
      expect(element).toHaveClass('text-xs');
    });

    it('applies sm size classes when size="sm"', () => {
      render(<CategoryTag category="Sports" size="sm" />);
      const element = screen.getByText('Sports');
      expect(element).toHaveClass('px-2');
      expect(element).toHaveClass('text-xs');
    });
  });

  describe('navigation', () => {
    it('generates correct default href when clickable', () => {
      render(<CategoryTag category="Politics" clickable />);
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('href', '/markets?category=politics');
    });

    it('encodes category name in URL', () => {
      render(<CategoryTag category="World Events" clickable />);
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('href', '/markets?category=world%20events');
    });

    it('uses custom href when provided', () => {
      render(<CategoryTag category="Tech" clickable href="/explore?cat=technology" />);
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('href', '/explore?cat=technology');
    });

    it('has correct aria-label when clickable', () => {
      render(<CategoryTag category="Crypto" clickable />);
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('aria-label', 'View Crypto markets');
    });
  });

  describe('tooltip', () => {
    it('shows full name in title for non-clickable tag with known category', () => {
      render(<CategoryTag category="Tech" />);
      const element = screen.getByText('Tech');
      expect(element).toHaveAttribute('title', 'Technology & Innovation');
    });

    it('does not show title for unknown category without full name', () => {
      render(<CategoryTag category="Unknown" />);
      const element = screen.getByText('Unknown');
      expect(element).not.toHaveAttribute('title');
    });

    it('shows descriptive title for clickable tag', () => {
      render(<CategoryTag category="Politics" clickable />);
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('title', 'Political Events & Elections - Click to view all Politics markets');
    });

    it('shows simple title for unknown clickable category', () => {
      render(<CategoryTag category="Custom" clickable />);
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('title', 'Click to view all Custom markets');
    });
  });

  describe('hover state', () => {
    it('has hover background class when clickable', () => {
      render(<CategoryTag category="Finance" clickable />);
      const link = screen.getByRole('link');
      expect(link).toHaveClass('hover:bg-yellow-100');
      expect(link).toHaveClass('cursor-pointer');
    });

    it('does not have hover class when not clickable', () => {
      render(<CategoryTag category="Finance" />);
      const element = screen.getByText('Finance');
      expect(element).not.toHaveClass('hover:bg-yellow-100');
    });
  });
});

// ============================================================================
// CategoryTagList Component Tests
// ============================================================================

describe('CategoryTagList', () => {
  describe('rendering', () => {
    it('renders all categories', () => {
      render(<CategoryTagList categories={['Politics', 'Crypto', 'Tech']} />);
      expect(screen.getByText('Politics')).toBeInTheDocument();
      expect(screen.getByText('Crypto')).toBeInTheDocument();
      expect(screen.getByText('Tech')).toBeInTheDocument();
    });

    it('returns null for empty categories array', () => {
      const { container } = render(<CategoryTagList categories={[]} />);
      expect(container.firstChild).toBeNull();
    });

    it('applies custom className to container', () => {
      const { container } = render(
        <CategoryTagList categories={['Sports']} className="custom-container" />
      );
      expect(container.firstChild).toHaveClass('custom-container');
    });

    it('passes clickable prop to all tags', () => {
      render(<CategoryTagList categories={['Politics', 'Crypto']} clickable />);
      const links = screen.getAllByRole('link');
      expect(links).toHaveLength(2);
    });

    it('passes size prop to all tags', () => {
      render(<CategoryTagList categories={['Sports', 'Tech']} size="sm" />);
      const elements = screen.getAllByText(/Sports|Tech/);
      elements.forEach(element => {
        expect(element).toHaveClass('px-2');
      });
    });
  });

  describe('truncation with maxVisible', () => {
    it('shows all categories when count equals maxVisible', () => {
      render(
        <CategoryTagList
          categories={['A', 'B', 'C']}
          maxVisible={3}
        />
      );
      expect(screen.getByText('A')).toBeInTheDocument();
      expect(screen.getByText('B')).toBeInTheDocument();
      expect(screen.getByText('C')).toBeInTheDocument();
      expect(screen.queryByText(/\+\d+ more/)).not.toBeInTheDocument();
    });

    it('shows all categories when count is less than maxVisible', () => {
      render(
        <CategoryTagList
          categories={['A', 'B']}
          maxVisible={5}
        />
      );
      expect(screen.getByText('A')).toBeInTheDocument();
      expect(screen.getByText('B')).toBeInTheDocument();
      expect(screen.queryByText(/\+\d+ more/)).not.toBeInTheDocument();
    });

    it('truncates and shows "+N more" when exceeding maxVisible', () => {
      render(
        <CategoryTagList
          categories={['Politics', 'Crypto', 'Tech', 'Sports', 'Science']}
          maxVisible={3}
        />
      );
      expect(screen.getByText('Politics')).toBeInTheDocument();
      expect(screen.getByText('Crypto')).toBeInTheDocument();
      expect(screen.getByText('Tech')).toBeInTheDocument();
      expect(screen.queryByText('Sports')).not.toBeInTheDocument();
      expect(screen.queryByText('Science')).not.toBeInTheDocument();
      expect(screen.getByText('+2 more')).toBeInTheDocument();
    });

    it('shows hidden categories in tooltip of "+N more"', () => {
      render(
        <CategoryTagList
          categories={['A', 'B', 'C', 'D', 'E']}
          maxVisible={2}
        />
      );
      const moreElement = screen.getByText('+3 more');
      expect(moreElement).toHaveAttribute('title', '+3 more: C, D, E');
    });

    it('applies size to "+N more" badge', () => {
      render(
        <CategoryTagList
          categories={['A', 'B', 'C']}
          maxVisible={1}
          size="sm"
        />
      );
      const moreElement = screen.getByText('+2 more');
      expect(moreElement).toHaveClass('px-2');
    });
  });

  describe('without maxVisible', () => {
    it('shows all categories without truncation', () => {
      render(
        <CategoryTagList
          categories={['A', 'B', 'C', 'D', 'E', 'F', 'G']}
        />
      );
      ['A', 'B', 'C', 'D', 'E', 'F', 'G'].forEach(cat => {
        expect(screen.getByText(cat)).toBeInTheDocument();
      });
      expect(screen.queryByText(/\+\d+ more/)).not.toBeInTheDocument();
    });
  });

  describe('container styling', () => {
    it('uses flex-wrap for multiple categories', () => {
      const { container } = render(
        <CategoryTagList categories={['A', 'B', 'C']} />
      );
      expect(container.firstChild).toHaveClass('flex');
      expect(container.firstChild).toHaveClass('flex-wrap');
      expect(container.firstChild).toHaveClass('items-center');
      expect(container.firstChild).toHaveClass('gap-1.5');
    });
  });
});

// ============================================================================
// Integration Tests
// ============================================================================

describe('CategoryTag integration', () => {
  it('supports multiple tags per event pattern', () => {
    const eventCategories = ['Politics', 'World', 'Economics'];
    render(<CategoryTagList categories={eventCategories} clickable />);

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(3);

    expect(links[0]).toHaveAttribute('href', '/markets?category=politics');
    expect(links[1]).toHaveAttribute('href', '/markets?category=world');
    expect(links[2]).toHaveAttribute('href', '/markets?category=economics');
  });

  it('handles mixed known and unknown categories', () => {
    render(
      <CategoryTagList
        categories={['Politics', 'CustomCategory', 'Crypto']}
        clickable
      />
    );

    // Politics should have blue colors
    const politics = screen.getByText('Politics');
    expect(politics).toHaveClass('bg-blue-50');

    // CustomCategory should have gray (default) colors
    const custom = screen.getByText('CustomCategory');
    expect(custom).toHaveClass('bg-gray-50');

    // Crypto should have orange colors
    const crypto = screen.getByText('Crypto');
    expect(crypto).toHaveClass('bg-orange-50');
  });
});
