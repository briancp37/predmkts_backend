/**
 * Event Header Component Tests
 *
 * Tests for:
 * - Helper functions (formatVolume, formatEndDate)
 * - CategoryBadge component
 * - EventHeader component
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/api/auth-context';
import {
  formatVolume,
  formatEndDate,
  CategoryBadge,
  EventHeader,
} from '@/components/event/event-header';

// ============================================================================
// Test Utilities
// ============================================================================

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          {children}
        </AuthProvider>
      </QueryClientProvider>
    );
  };
}

// ============================================================================
// formatVolume Tests
// ============================================================================

describe('formatVolume', () => {
  it('formats values under $1,000', () => {
    expect(formatVolume(0)).toBe('$0');
    expect(formatVolume(100)).toBe('$100');
    expect(formatVolume(999)).toBe('$999');
  });

  it('formats values in thousands with K suffix', () => {
    expect(formatVolume(1000)).toBe('$1.0K');
    expect(formatVolume(1500)).toBe('$1.5K');
    expect(formatVolume(66109)).toBe('$66.1K');
    expect(formatVolume(999999)).toBe('$1000.0K');
  });

  it('formats values in millions with M suffix', () => {
    expect(formatVolume(1000000)).toBe('$1.0M');
    expect(formatVolume(1500000)).toBe('$1.5M');
    expect(formatVolume(25600000)).toBe('$25.6M');
  });
});

// ============================================================================
// formatEndDate Tests
// ============================================================================

describe('formatEndDate', () => {
  beforeEach(() => {
    // Mock current date to 2026-02-06
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-02-06T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('past dates', () => {
    it('returns "Ended today" for today', () => {
      const result = formatEndDate('2026-02-06T06:00:00Z');
      expect(result.text).toBe('Ended today');
      expect(result.isPast).toBe(true);
    });

    it('returns "Ended yesterday" for yesterday', () => {
      const result = formatEndDate('2026-02-05T12:00:00Z');
      expect(result.text).toBe('Ended yesterday');
      expect(result.isPast).toBe(true);
    });

    it('returns relative days for recent past', () => {
      const result = formatEndDate('2026-02-03T12:00:00Z');
      expect(result.text).toBe('Ended 3 days ago');
      expect(result.isPast).toBe(true);
    });

    it('returns formatted date for older dates', () => {
      const result = formatEndDate('2026-01-15T12:00:00Z');
      expect(result.text).toBe('Ended Jan 15, 2026');
      expect(result.isPast).toBe(true);
    });
  });

  describe('future dates', () => {
    it('returns "Ends today" for later today', () => {
      const result = formatEndDate('2026-02-06T23:59:59Z');
      expect(result.text).toBe('Ends today');
      expect(result.isPast).toBe(false);
    });

    it('returns "Ends tomorrow" for tomorrow', () => {
      const result = formatEndDate('2026-02-07T12:00:00Z');
      expect(result.text).toBe('Ends tomorrow');
      expect(result.isPast).toBe(false);
    });

    it('returns relative days for near future', () => {
      const result = formatEndDate('2026-02-10T12:00:00Z');
      expect(result.text).toBe('Ends in 4 days');
      expect(result.isPast).toBe(false);
    });

    it('returns formatted date for far future', () => {
      const result = formatEndDate('2026-06-30T23:59:59Z');
      expect(result.text).toBe('Ends Jun 30, 2026');
      expect(result.isPast).toBe(false);
    });
  });
});

// ============================================================================
// CategoryBadge Tests
// ============================================================================

describe('CategoryBadge', () => {
  it('renders category text', () => {
    render(<CategoryBadge category="Politics" />);
    expect(screen.getByText('Politics')).toBeInTheDocument();
  });

  it('applies blue colors for Politics category', () => {
    const { container } = render(<CategoryBadge category="Politics" />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('bg-blue-50');
    expect(badge).toHaveClass('text-blue-700');
    expect(badge).toHaveClass('border-blue-200');
  });

  it('applies orange colors for Crypto category', () => {
    const { container } = render(<CategoryBadge category="Crypto" />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('bg-orange-50');
    expect(badge).toHaveClass('text-orange-700');
  });

  it('applies purple colors for Tech category', () => {
    const { container } = render(<CategoryBadge category="Tech" />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('bg-purple-50');
    expect(badge).toHaveClass('text-purple-700');
  });

  it('applies default gray colors for unknown category', () => {
    const { container } = render(<CategoryBadge category="Unknown" />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('bg-gray-50');
    expect(badge).toHaveClass('text-gray-700');
  });

  it('accepts custom className', () => {
    const { container } = render(<CategoryBadge category="Tech" className="my-class" />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('my-class');
  });
});

// ============================================================================
// EventHeader Tests
// ============================================================================

describe('EventHeader', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-02-06T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders title with proper typography', () => {
    render(
      <EventHeader title="Will Bitcoin reach $100K by end of 2025?" />,
      { wrapper: createWrapper() }
    );
    const title = screen.getByRole('heading', { level: 1 });
    expect(title).toHaveTextContent('Will Bitcoin reach $100K by end of 2025?');
    expect(title).toHaveClass('text-2xl');
    expect(title).toHaveClass('font-bold');
  });

  it('renders category badge when provided', () => {
    render(
      <EventHeader title="Test Event" category="Crypto" />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('Crypto')).toBeInTheDocument();
  });

  it('does not render category badge when not provided', () => {
    render(
      <EventHeader title="Test Event" />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByText('Crypto')).not.toBeInTheDocument();
  });

  it('renders probability with chance suffix', () => {
    render(
      <EventHeader title="Test Event" probability={0.12} />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('12%')).toBeInTheDocument();
    expect(screen.getByText('chance')).toBeInTheDocument();
  });

  it('renders probability change when provided', () => {
    render(
      <EventHeader title="Test Event" probability={0.12} probabilityChange24h={0.02} />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('↑')).toBeInTheDocument();
    expect(screen.getByText('2.0%')).toBeInTheDocument();
    expect(screen.getByText('24h')).toBeInTheDocument();
  });

  it('does not render probability change when zero', () => {
    render(
      <EventHeader title="Test Event" probability={0.12} probabilityChange24h={0} />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByText('↑')).not.toBeInTheDocument();
    expect(screen.queryByText('↓')).not.toBeInTheDocument();
  });

  it('renders volume with proper formatting', () => {
    render(
      <EventHeader title="Test Event" volume={66109} />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('$66.1K Vol.')).toBeInTheDocument();
  });

  it('renders end date with relative time', () => {
    render(
      <EventHeader title="Test Event" endDate="2026-06-30T23:59:59Z" />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('Ends Jun 30, 2026')).toBeInTheDocument();
  });

  it('renders resolved badge when resolved is true', () => {
    render(
      <EventHeader title="Test Event" resolved />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('Resolved')).toBeInTheDocument();
  });

  it('does not show watchlist button when not authenticated', () => {
    render(
      <EventHeader title="Test Event" marketId="market-123" />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByRole('button', { name: /watch/i })).not.toBeInTheDocument();
  });

  it('renders all metadata together', () => {
    render(
      <EventHeader
        title="Will Bitcoin reach $100K by end of 2025?"
        category="Crypto"
        probability={0.12}
        probabilityChange24h={0.02}
        volume={66109}
        endDate="2026-06-30T23:59:59Z"
        marketId="market-123"
      />,
      { wrapper: createWrapper() }
    );

    // Check all elements are present
    expect(screen.getByText('Will Bitcoin reach $100K by end of 2025?')).toBeInTheDocument();
    expect(screen.getByText('Crypto')).toBeInTheDocument();
    expect(screen.getByText('12%')).toBeInTheDocument();
    expect(screen.getByText('chance')).toBeInTheDocument();
    expect(screen.getByText('$66.1K Vol.')).toBeInTheDocument();
    expect(screen.getByText('Ends Jun 30, 2026')).toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(
      <EventHeader title="Test Event" className="my-custom-class" />,
      { wrapper: createWrapper() }
    );
    expect(container.firstChild).toHaveClass('my-custom-class');
  });

  it('handles null/undefined values gracefully', () => {
    render(
      <EventHeader
        title="Test Event"
        category={null}
        probability={null}
        probabilityChange24h={null}
        volume={null}
        endDate={null}
        marketId={null}
      />,
      { wrapper: createWrapper() }
    );

    // Only title should be present
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Test Event');
    expect(screen.queryByText('chance')).not.toBeInTheDocument();
    expect(screen.queryByText(/Vol\./)).not.toBeInTheDocument();
    expect(screen.queryByText(/Ends/)).not.toBeInTheDocument();
  });
});
