/**
 * Market Details Panel Component Tests
 *
 * Tests for:
 * - Helper functions (formatCurrency, formatFullDateTime, formatRelativeTime, truncateAddress)
 * - MarketDetailsPanel component
 * - Copy to clipboard functionality
 * - Expandable additional metadata section
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import {
  formatCurrency,
  formatFullDateTime,
  formatRelativeTime,
  truncateAddress,
  MarketDetailsPanel,
} from '@/components/event/market-details-panel';

// ============================================================================
// Mock clipboard API
// ============================================================================

const mockClipboard = {
  writeText: vi.fn().mockResolvedValue(undefined),
};

beforeEach(() => {
  vi.stubGlobal('navigator', {
    clipboard: mockClipboard,
  });
  mockClipboard.writeText.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ============================================================================
// formatCurrency Tests
// ============================================================================

describe('formatCurrency', () => {
  it('formats values under $1,000 with 2 decimal places', () => {
    expect(formatCurrency(0)).toBe('$0.00');
    expect(formatCurrency(0.5)).toBe('$0.50');
    expect(formatCurrency(100)).toBe('$100.00');
    expect(formatCurrency(999.99)).toBe('$999.99');
  });

  it('formats values $1,000 to $999,999 with locale formatting', () => {
    expect(formatCurrency(1000)).toBe('$1,000');
    expect(formatCurrency(1500)).toBe('$1,500');
    expect(formatCurrency(66109)).toBe('$66,109');
    expect(formatCurrency(999999)).toBe('$999,999');
  });

  it('formats values in millions with M suffix and 2 decimals', () => {
    expect(formatCurrency(1000000)).toBe('$1.00M');
    expect(formatCurrency(1500000)).toBe('$1.50M');
    expect(formatCurrency(25600000)).toBe('$25.60M');
    expect(formatCurrency(999999999)).toBe('$1000.00M');
  });

  it('formats values in billions with B suffix and 2 decimals', () => {
    expect(formatCurrency(1000000000)).toBe('$1.00B');
    expect(formatCurrency(1500000000)).toBe('$1.50B');
    expect(formatCurrency(25600000000)).toBe('$25.60B');
  });
});

// ============================================================================
// formatFullDateTime Tests
// ============================================================================

describe('formatFullDateTime', () => {
  it('formats a date with full date and time', () => {
    // Note: Test output depends on locale and timezone, checking year which is stable
    const result = formatFullDateTime('2026-06-30T23:59:59Z');
    expect(result).toContain('2026');
    // Should include AM or PM
    expect(result).toMatch(/(AM|PM)/);
  });

  it('handles midnight UTC correctly', () => {
    // Midnight UTC will be shown in local time, so just verify it's a valid date string
    const result = formatFullDateTime('2026-01-15T00:00:00Z');
    expect(result).toContain('Jan');
    expect(result).toContain('2026');
    expect(result).toMatch(/(AM|PM)/);
  });

  it('handles noon UTC correctly', () => {
    const result = formatFullDateTime('2026-07-04T12:00:00Z');
    expect(result).toContain('Jul');
    expect(result).toContain('2026');
    expect(result).toMatch(/(AM|PM)/);
  });
});

// ============================================================================
// formatRelativeTime Tests
// ============================================================================

describe('formatRelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-02-06T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "just now" for very recent times', () => {
    expect(formatRelativeTime('2026-02-06T11:59:30Z')).toBe('just now');
  });

  it('returns "1 minute ago" for 1 minute', () => {
    expect(formatRelativeTime('2026-02-06T11:59:00Z')).toBe('1 minute ago');
  });

  it('returns plural minutes for multiple minutes', () => {
    expect(formatRelativeTime('2026-02-06T11:55:00Z')).toBe('5 minutes ago');
    expect(formatRelativeTime('2026-02-06T11:30:00Z')).toBe('30 minutes ago');
  });

  it('returns "1 hour ago" for 1 hour', () => {
    expect(formatRelativeTime('2026-02-06T11:00:00Z')).toBe('1 hour ago');
  });

  it('returns plural hours for multiple hours', () => {
    expect(formatRelativeTime('2026-02-06T06:00:00Z')).toBe('6 hours ago');
  });

  it('returns "yesterday" for 1 day ago', () => {
    expect(formatRelativeTime('2026-02-05T12:00:00Z')).toBe('yesterday');
  });

  it('returns plural days for 2-6 days ago', () => {
    expect(formatRelativeTime('2026-02-04T12:00:00Z')).toBe('2 days ago');
    expect(formatRelativeTime('2026-02-01T12:00:00Z')).toBe('5 days ago');
  });

  it('returns "1 week ago" for 1 week', () => {
    expect(formatRelativeTime('2026-01-30T12:00:00Z')).toBe('1 week ago');
  });

  it('returns plural weeks for 2-3 weeks ago', () => {
    expect(formatRelativeTime('2026-01-23T12:00:00Z')).toBe('2 weeks ago');
  });

  it('returns "1 month ago" for 1 month', () => {
    expect(formatRelativeTime('2026-01-06T12:00:00Z')).toBe('1 month ago');
  });

  it('returns plural months for multiple months ago', () => {
    expect(formatRelativeTime('2025-11-06T12:00:00Z')).toBe('3 months ago');
  });

  it('returns "1 year ago" for 1 year', () => {
    expect(formatRelativeTime('2025-02-06T12:00:00Z')).toBe('1 year ago');
  });

  it('returns plural years for multiple years ago', () => {
    expect(formatRelativeTime('2024-02-06T12:00:00Z')).toBe('2 years ago');
  });
});

// ============================================================================
// truncateAddress Tests
// ============================================================================

describe('truncateAddress', () => {
  it('truncates long addresses with default params', () => {
    expect(truncateAddress('0x1234567890abcdef1234567890abcdef12345678'))
      .toBe('0x1234...5678');
  });

  it('returns full string if shorter than truncation threshold', () => {
    expect(truncateAddress('0x12345678')).toBe('0x12345678');
    expect(truncateAddress('short')).toBe('short');
  });

  it('respects custom start and end character counts', () => {
    expect(truncateAddress('0x1234567890abcdef1234567890abcdef12345678', 8, 6))
      .toBe('0x123456...345678');
    expect(truncateAddress('0x1234567890abcdef1234567890abcdef12345678', 4, 4))
      .toBe('0x12...5678');
  });

  it('handles edge case of exact threshold length', () => {
    // With default 6 start + 4 end + 3 for "..." = 13 char threshold
    // A 13-char string should not be truncated
    expect(truncateAddress('1234567890123')).toBe('1234567890123');
  });
});

// ============================================================================
// MarketDetailsPanel Component Tests
// ============================================================================

describe('MarketDetailsPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-02-06T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the component title', () => {
    render(<MarketDetailsPanel />);
    expect(screen.getByText('Market Details')).toBeInTheDocument();
  });

  it('displays volume with proper formatting', () => {
    render(<MarketDetailsPanel volume={66109} />);
    expect(screen.getByText('Total Volume')).toBeInTheDocument();
    expect(screen.getByText('$66,109')).toBeInTheDocument();
  });

  it('displays liquidity with proper formatting', () => {
    render(<MarketDetailsPanel liquidity={25000} />);
    expect(screen.getByText('Liquidity')).toBeInTheDocument();
    expect(screen.getByText('$25,000')).toBeInTheDocument();
  });

  it('displays end date with full date and time', () => {
    render(<MarketDetailsPanel endDate="2026-06-30T23:59:59Z" />);
    expect(screen.getByText('Resolution Date')).toBeInTheDocument();
    // Check that the date contains expected parts
    const dateElement = screen.getByText(/Jun.*30.*2026/);
    expect(dateElement).toBeInTheDocument();
  });

  it('displays created date with relative time', () => {
    render(<MarketDetailsPanel createdAt="2026-01-23T10:30:00Z" />);
    expect(screen.getByText('Created')).toBeInTheDocument();
    expect(screen.getByText('2 weeks ago')).toBeInTheDocument();
  });

  it('displays truncated resolver address with copy button', () => {
    render(<MarketDetailsPanel resolverAddress="0x1234567890abcdef1234567890abcdef12345678" />);
    expect(screen.getByText('Resolver')).toBeInTheDocument();
    expect(screen.getByText('0x1234...5678')).toBeInTheDocument();
    expect(screen.getByLabelText('Copy Resolver')).toBeInTheDocument();
  });

  it('displays truncated market ID with copy button', () => {
    render(<MarketDetailsPanel marketId="market-1234567890abcdef" />);
    expect(screen.getByText('Market ID')).toBeInTheDocument();
    expect(screen.getByText('market-1...abcdef')).toBeInTheDocument();
    expect(screen.getByLabelText('Copy Market ID')).toBeInTheDocument();
  });

  it('renders nothing for null/undefined values', () => {
    render(<MarketDetailsPanel volume={null} endDate={null} />);
    expect(screen.queryByText('Total Volume')).not.toBeInTheDocument();
    expect(screen.queryByText('Resolution Date')).not.toBeInTheDocument();
  });

  describe('expandable additional metadata', () => {
    it('shows expand button when additional metadata is available', () => {
      render(<MarketDetailsPanel conditionId="0xabcdef123456789" />);
      expect(screen.getByText('Additional Details')).toBeInTheDocument();
    });

    it('does not show expand button when no additional metadata', () => {
      render(<MarketDetailsPanel volume={1000} />);
      expect(screen.queryByText('Additional Details')).not.toBeInTheDocument();
    });

    it('expands to show condition ID when clicked', () => {
      render(<MarketDetailsPanel conditionId="0x1234567890abcdef1234567890abcdef12345678" />);

      // Initially not visible
      expect(screen.queryByText('Condition ID')).not.toBeInTheDocument();

      // Click to expand
      fireEvent.click(screen.getByText('Additional Details'));

      // Now visible
      expect(screen.getByText('Condition ID')).toBeInTheDocument();
    });

    it('expands to show slug when clicked', () => {
      render(<MarketDetailsPanel slug="will-bitcoin-reach-100k" />);

      // Initially not visible
      expect(screen.queryByText('Slug')).not.toBeInTheDocument();

      // Click to expand
      fireEvent.click(screen.getByText('Additional Details'));

      // Now visible
      expect(screen.getByText('Slug')).toBeInTheDocument();
      expect(screen.getByText('will-bitcoin-reach-100k')).toBeInTheDocument();
    });

    it('truncates long slugs', () => {
      const longSlug = 'will-the-price-of-bitcoin-reach-100000-dollars-by-end-of-2025';
      render(<MarketDetailsPanel slug={longSlug} />);

      fireEvent.click(screen.getByText('Additional Details'));

      // Should be truncated to 27 chars + "..."
      expect(screen.getByText('will-the-price-of-bitcoin-r...')).toBeInTheDocument();
    });

    it('collapses when clicked again', () => {
      render(<MarketDetailsPanel conditionId="0x1234567890abcdef1234567890abcdef12345678" />);

      // Expand
      fireEvent.click(screen.getByText('Additional Details'));
      expect(screen.getByText('Condition ID')).toBeInTheDocument();

      // Collapse
      fireEvent.click(screen.getByText('Additional Details'));
      expect(screen.queryByText('Condition ID')).not.toBeInTheDocument();
    });

    it('has correct aria-expanded state', () => {
      render(<MarketDetailsPanel conditionId="0x123" />);

      const button = screen.getByText('Additional Details').closest('button');
      expect(button).toHaveAttribute('aria-expanded', 'false');

      fireEvent.click(button!);
      expect(button).toHaveAttribute('aria-expanded', 'true');
    });
  });

  describe('copy button presence', () => {
    it('shows copy button for resolver address', () => {
      render(<MarketDetailsPanel resolverAddress="0x1234567890abcdef1234567890abcdef12345678" />);
      expect(screen.getByLabelText('Copy Resolver')).toBeInTheDocument();
    });

    it('shows copy button for market ID', () => {
      render(<MarketDetailsPanel marketId="market-1234567890abcdef" />);
      expect(screen.getByLabelText('Copy Market ID')).toBeInTheDocument();
    });
  });

  describe('displays all fields together', () => {
    it('renders all provided fields correctly', () => {
      render(
        <MarketDetailsPanel
          volume={1500000}
          liquidity={50000}
          endDate="2026-06-30T23:59:59Z"
          createdAt="2026-01-06T12:00:00Z"
          resolverAddress="0xabcdef1234567890"
          marketId="mkt-12345678"
          conditionId="0xcondition123"
          slug="test-market-slug"
        />
      );

      // Check main fields
      expect(screen.getByText('$1.50M')).toBeInTheDocument();
      expect(screen.getByText('$50,000')).toBeInTheDocument();
      expect(screen.getByText('1 month ago')).toBeInTheDocument();

      // Expand and check additional fields
      fireEvent.click(screen.getByText('Additional Details'));
      expect(screen.getByText('Condition ID')).toBeInTheDocument();
      expect(screen.getByText('Slug')).toBeInTheDocument();
    });
  });

  it('applies custom className', () => {
    const { container } = render(<MarketDetailsPanel className="custom-class" />);
    expect(container.firstChild).toHaveClass('custom-class');
  });
});

// ============================================================================
// Copy to Clipboard Tests (separate describe to avoid fake timer issues)
// ============================================================================

describe('MarketDetailsPanel copy to clipboard', () => {
  it('copies resolver address to clipboard when copy button is clicked', async () => {
    const address = '0x1234567890abcdef1234567890abcdef12345678';
    render(<MarketDetailsPanel resolverAddress={address} />);

    fireEvent.click(screen.getByLabelText('Copy Resolver'));

    await waitFor(() => {
      expect(mockClipboard.writeText).toHaveBeenCalledWith(address);
    });
  });

  it('copies market ID to clipboard when copy button is clicked', async () => {
    const marketId = 'market-1234567890abcdef';
    render(<MarketDetailsPanel marketId={marketId} />);

    fireEvent.click(screen.getByLabelText('Copy Market ID'));

    await waitFor(() => {
      expect(mockClipboard.writeText).toHaveBeenCalledWith(marketId);
    });
  });

  it('shows checkmark after successful copy', async () => {
    render(<MarketDetailsPanel resolverAddress="0x123456789" />);

    fireEvent.click(screen.getByLabelText('Copy Resolver'));

    await waitFor(() => {
      expect(screen.getByLabelText('Copied!')).toBeInTheDocument();
    });
  });

  it('reverts to copy icon after timeout', async () => {
    vi.useFakeTimers();
    render(<MarketDetailsPanel resolverAddress="0x123456789" />);

    // Click copy and wait for state update
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Copy Resolver'));
      // Allow the promise to resolve
      await Promise.resolve();
    });

    // Verify checkmark is shown
    expect(screen.getByLabelText('Copied!')).toBeInTheDocument();

    // Advance timers
    act(() => {
      vi.advanceTimersByTime(2100);
    });

    // Should revert to copy icon
    expect(screen.getByLabelText('Copy Resolver')).toBeInTheDocument();

    vi.useRealTimers();
  });
});
