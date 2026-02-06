/**
 * Loading skeleton component tests
 *
 * Tests the skeleton and loading state UI components:
 * - Skeleton base component
 * - Specialized skeletons (MarketCard, TraderCard, etc.)
 * - Spinner component
 * - StaleIndicator
 * - LoadingButton
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  Skeleton,
  MarketCardSkeleton,
  MarketTableSkeleton,
  TraderCardSkeleton,
  TrackedTraderRowSkeleton,
  ActivityRowSkeleton,
  WatchlistItemSkeleton,
  LeaderboardRowSkeleton,
  ListSkeleton,
  Spinner,
  RefetchingOverlay,
  StaleIndicator,
  LoadingButton,
} from '@/components/loading-skeleton';

describe('Skeleton', () => {
  it('renders with default classes', () => {
    const { container } = render(<Skeleton />);

    const skeleton = container.firstChild;
    expect(skeleton).toHaveClass('bg-gradient-to-r');
    expect(skeleton).toHaveClass('animate-shimmer');
  });

  it('accepts custom className', () => {
    const { container } = render(<Skeleton className="h-10 w-full" />);

    const skeleton = container.firstChild;
    expect(skeleton).toHaveClass('h-10');
    expect(skeleton).toHaveClass('w-full');
  });
});

describe('MarketCardSkeleton', () => {
  it('renders market card skeleton structure', () => {
    const { container } = render(<MarketCardSkeleton />);

    // Check for the card container
    const card = container.querySelector('.rounded-lg');
    expect(card).toBeInTheDocument();

    // Check for multiple skeleton elements
    const skeletons = container.querySelectorAll('[class*="animate-shimmer"]');
    expect(skeletons.length).toBeGreaterThan(5);
  });
});

describe('MarketTableSkeleton', () => {
  it('renders correct number of rows', () => {
    const { container } = render(<MarketTableSkeleton rows={5} />);

    // Each TableRowSkeleton has a border-b class
    const rows = container.querySelectorAll('[class*="border-b"]');
    // +1 for header border
    expect(rows.length).toBe(6);
  });

  it('defaults to 10 rows', () => {
    const { container } = render(<MarketTableSkeleton />);

    const rows = container.querySelectorAll('[class*="border-b"]');
    expect(rows.length).toBe(11);
  });
});

describe('TraderCardSkeleton', () => {
  it('renders trader card skeleton', () => {
    const { container } = render(<TraderCardSkeleton />);

    const card = container.querySelector('.rounded-lg');
    expect(card).toBeInTheDocument();
    expect(card).toHaveClass('animate-pulse');
  });
});

describe('TrackedTraderRowSkeleton', () => {
  it('renders with animation delay based on index', () => {
    const { container } = render(<TrackedTraderRowSkeleton index={2} />);

    const row = container.firstChild;
    expect(row).toHaveStyle({ animationDelay: '100ms' });
  });
});

describe('ActivityRowSkeleton', () => {
  it('renders activity row with staggered animation', () => {
    const { container } = render(<ActivityRowSkeleton index={3} />);

    const row = container.firstChild;
    expect(row).toHaveStyle({ animationDelay: '90ms' });
  });
});

describe('WatchlistItemSkeleton', () => {
  it('renders watchlist item skeleton', () => {
    const { container } = render(<WatchlistItemSkeleton index={0} />);

    expect(container.firstChild).toHaveClass('flex');
    expect(container.firstChild).toHaveClass('items-center');
  });
});

describe('LeaderboardRowSkeleton', () => {
  it('renders leaderboard row skeleton', () => {
    const { container } = render(<LeaderboardRowSkeleton index={1} />);

    const row = container.firstChild;
    expect(row).toHaveStyle({ animationDelay: '30ms' });
  });
});

describe('ListSkeleton', () => {
  it('renders correct number of items using children function', () => {
    render(
      <ListSkeleton count={3}>
        {(index) => <div data-testid={`item-${index}`}>Item {index}</div>}
      </ListSkeleton>
    );

    expect(screen.getByTestId('item-0')).toBeInTheDocument();
    expect(screen.getByTestId('item-1')).toBeInTheDocument();
    expect(screen.getByTestId('item-2')).toBeInTheDocument();
    expect(screen.queryByTestId('item-3')).not.toBeInTheDocument();
  });

  it('defaults to 5 items', () => {
    const { container } = render(
      <ListSkeleton>{(index) => <div data-testid={`item-${index}`} />}</ListSkeleton>
    );

    expect(container.querySelectorAll('[data-testid^="item-"]')).toHaveLength(5);
  });
});

describe('Spinner', () => {
  it('renders with default medium size', () => {
    const { container } = render(<Spinner />);

    const spinner = container.firstChild;
    expect(spinner).toHaveClass('h-6');
    expect(spinner).toHaveClass('w-6');
    expect(spinner).toHaveClass('animate-spin');
  });

  it('renders small size', () => {
    const { container } = render(<Spinner size="sm" />);

    const spinner = container.firstChild;
    expect(spinner).toHaveClass('h-4');
    expect(spinner).toHaveClass('w-4');
  });

  it('renders large size', () => {
    const { container } = render(<Spinner size="lg" />);

    const spinner = container.firstChild;
    expect(spinner).toHaveClass('h-8');
    expect(spinner).toHaveClass('w-8');
  });

  it('accepts custom className', () => {
    const { container } = render(<Spinner className="text-blue-500" />);

    const spinner = container.firstChild;
    expect(spinner).toHaveClass('text-blue-500');
  });
});

describe('RefetchingOverlay', () => {
  it('does not show overlay when not refetching', () => {
    render(
      <RefetchingOverlay isRefetching={false}>
        <div>Content</div>
      </RefetchingOverlay>
    );

    expect(screen.getByText('Content')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('shows overlay with spinner when refetching', () => {
    const { container } = render(
      <RefetchingOverlay isRefetching={true}>
        <div>Content</div>
      </RefetchingOverlay>
    );

    expect(screen.getByText('Content')).toBeInTheDocument();
    // Check for the overlay element
    const overlay = container.querySelector('.absolute.inset-0');
    expect(overlay).toBeInTheDocument();
    // Check for spinner inside overlay
    const spinner = overlay?.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });
});

describe('StaleIndicator', () => {
  it('returns null when neither stale nor refetching', () => {
    const { container } = render(<StaleIndicator isStale={false} isRefetching={false} />);

    expect(container.firstChild).toBeNull();
  });

  it('shows stale indicator when data is stale', () => {
    render(<StaleIndicator isStale={true} isRefetching={false} />);

    expect(screen.getByText(/stale data/i)).toBeInTheDocument();
  });

  it('shows updating indicator when refetching', () => {
    render(<StaleIndicator isStale={false} isRefetching={true} />);

    expect(screen.getByText(/updating/i)).toBeInTheDocument();
  });

  it('prioritizes refetching over stale display', () => {
    render(<StaleIndicator isStale={true} isRefetching={true} />);

    expect(screen.getByText(/updating/i)).toBeInTheDocument();
    expect(screen.queryByText(/stale data/i)).not.toBeInTheDocument();
  });
});

describe('LoadingButton', () => {
  it('renders children when not loading', () => {
    render(<LoadingButton>Submit</LoadingButton>);

    expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument();
  });

  it('shows loading text when loading', () => {
    render(
      <LoadingButton isLoading loadingText="Submitting...">
        Submit
      </LoadingButton>
    );

    expect(screen.getByRole('button', { name: /submitting/i })).toBeInTheDocument();
  });

  it('is disabled when loading', () => {
    render(
      <LoadingButton isLoading>Submit</LoadingButton>
    );

    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is disabled when disabled prop is true', () => {
    render(
      <LoadingButton disabled>Submit</LoadingButton>
    );

    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('shows spinner when loading', () => {
    const { container } = render(
      <LoadingButton isLoading>Submit</LoadingButton>
    );

    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });
});
