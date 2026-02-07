/**
 * Resolution Rules Component Tests
 *
 * Tests for:
 * - ResolutionRules component rendering
 * - Description display with collapsible long text
 * - Resolution criteria parsing and highlighting
 * - Resolver information display
 * - Resolved status banner
 * - Propose Resolution button (disabled placeholder)
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ResolutionRules } from '@/components/event/resolution-rules';

// ============================================================================
// Basic Rendering Tests
// ============================================================================

describe('ResolutionRules', () => {
  it('renders the component title', () => {
    render(<ResolutionRules />);
    expect(screen.getByText('Resolution Rules')).toBeInTheDocument();
  });

  it('displays empty state when no description is provided', () => {
    render(<ResolutionRules />);
    expect(
      screen.getByText('No resolution rules available for this market.')
    ).toBeInTheDocument();
  });

  it('displays empty state for null description', () => {
    render(<ResolutionRules description={null} />);
    expect(
      screen.getByText('No resolution rules available for this market.')
    ).toBeInTheDocument();
  });

  it('displays empty state for empty string description', () => {
    render(<ResolutionRules description="   " />);
    expect(
      screen.getByText('No resolution rules available for this market.')
    ).toBeInTheDocument();
  });

  it('displays description text', () => {
    render(
      <ResolutionRules description="This market will resolve to Yes if Bitcoin reaches $100,000 by the end of 2026." />
    );
    expect(
      screen.getByText(/This market will resolve to Yes if Bitcoin reaches/)
    ).toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(<ResolutionRules className="custom-class" />);
    expect(container.firstChild).toHaveClass('custom-class');
  });
});

// ============================================================================
// Collapsible Description Tests
// ============================================================================

describe('ResolutionRules collapsible description', () => {
  const shortDescription = 'This is a short description.';
  const longDescription = `This market will resolve based on the official results announced by the relevant authority.
  The resolution will take into account multiple factors including but not limited to official government data,
  verified news sources, and market participant consensus. In case of disputes, the UMA Optimistic Oracle will
  serve as the final arbiter of truth. Additional considerations include timing of the resolution, which must
  occur within 30 days of the event conclusion. Any appeals must be filed within 7 days of the initial resolution.
  The market creator reserves the right to clarify ambiguous terms prior to resolution. All participants should
  carefully read and understand these rules before trading. Markets may be invalidated if the underlying event
  is cancelled or significantly altered. In such cases, positions will be refunded at their original purchase price.`;

  it('does not show expand button for short descriptions', () => {
    render(<ResolutionRules description={shortDescription} />);
    expect(screen.queryByText('Show more')).not.toBeInTheDocument();
    expect(screen.queryByText('Show less')).not.toBeInTheDocument();
  });

  it('shows expand button for long descriptions', () => {
    render(<ResolutionRules description={longDescription} />);
    expect(screen.getByText('Show more')).toBeInTheDocument();
  });

  it('truncates long descriptions by default', () => {
    render(<ResolutionRules description={longDescription} />);
    // Should show truncated text with ellipsis
    expect(screen.getByText(/\.\.\./)).toBeInTheDocument();
  });

  it('expands description when Show more is clicked', () => {
    render(<ResolutionRules description={longDescription} />);

    // Click expand
    fireEvent.click(screen.getByText('Show more'));

    // Should now show Show less
    expect(screen.getByText('Show less')).toBeInTheDocument();
    expect(screen.queryByText('Show more')).not.toBeInTheDocument();
  });

  it('collapses description when Show less is clicked', () => {
    render(<ResolutionRules description={longDescription} />);

    // Expand
    fireEvent.click(screen.getByText('Show more'));
    expect(screen.getByText('Show less')).toBeInTheDocument();

    // Collapse
    fireEvent.click(screen.getByText('Show less'));
    expect(screen.getByText('Show more')).toBeInTheDocument();
  });

  it('has correct aria-expanded state', () => {
    render(<ResolutionRules description={longDescription} />);

    const button = screen.getByText('Show more').closest('button');
    expect(button).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(button!);
    expect(button).toHaveAttribute('aria-expanded', 'true');
  });
});

// ============================================================================
// Resolution Criteria Parsing Tests
// ============================================================================

describe('ResolutionRules criteria parsing', () => {
  it('extracts and displays bullet point criteria', () => {
    const descriptionWithBullets = `This market resolves based on official data.

    - Bitcoin must reach $100,000
    - The price must be sustained for 24 hours
    - CoinGecko will be the official source`;

    render(<ResolutionRules description={descriptionWithBullets} />);

    expect(screen.getByText('Key Resolution Criteria')).toBeInTheDocument();
    expect(screen.getByText('Bitcoin must reach $100,000')).toBeInTheDocument();
    expect(
      screen.getByText('The price must be sustained for 24 hours')
    ).toBeInTheDocument();
    expect(
      screen.getByText('CoinGecko will be the official source')
    ).toBeInTheDocument();
  });

  it('extracts numbered criteria', () => {
    const descriptionWithNumbers = `Resolution rules:

    1. First condition must be met
    2. Second condition must be verified
    3) Third condition is optional`;

    render(<ResolutionRules description={descriptionWithNumbers} />);

    expect(screen.getByText('First condition must be met')).toBeInTheDocument();
    expect(
      screen.getByText('Second condition must be verified')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Third condition is optional')
    ).toBeInTheDocument();
  });

  it('extracts asterisk bullet points', () => {
    const descriptionWithAsterisks = `Rules:

    * Must happen before deadline
    * Official announcement required`;

    render(<ResolutionRules description={descriptionWithAsterisks} />);

    expect(
      screen.getByText('Must happen before deadline')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Official announcement required')
    ).toBeInTheDocument();
  });

  it('does not show criteria section when no bullet points', () => {
    render(
      <ResolutionRules description="This is a plain description without any bullet points or numbered lists." />
    );

    expect(screen.queryByText('Key Resolution Criteria')).not.toBeInTheDocument();
  });
});

// ============================================================================
// Resolver Information Tests
// ============================================================================

describe('ResolutionRules resolver information', () => {
  it('displays resolver type', () => {
    render(<ResolutionRules resolverType="UMA Optimistic Oracle" />);

    expect(screen.getByText('Resolution Information')).toBeInTheDocument();
    expect(screen.getByText('Resolver:')).toBeInTheDocument();
    expect(screen.getByText('UMA Optimistic Oracle')).toBeInTheDocument();
  });

  it('displays resolution source', () => {
    render(<ResolutionRules resolutionSource="Official government data" />);

    expect(screen.getByText('Resolution Information')).toBeInTheDocument();
    expect(screen.getByText('Source:')).toBeInTheDocument();
    expect(screen.getByText('Official government data')).toBeInTheDocument();
  });

  it('displays both resolver type and source', () => {
    render(
      <ResolutionRules
        resolverType="Polymarket"
        resolutionSource="CoinGecko price data"
      />
    );

    expect(screen.getByText('Resolver:')).toBeInTheDocument();
    expect(screen.getByText('Polymarket')).toBeInTheDocument();
    expect(screen.getByText('Source:')).toBeInTheDocument();
    expect(screen.getByText('CoinGecko price data')).toBeInTheDocument();
  });

  it('does not show resolver section when no resolver info provided', () => {
    render(<ResolutionRules description="Some description" />);

    expect(
      screen.queryByText('Resolution Information')
    ).not.toBeInTheDocument();
  });

  it('handles null resolver values', () => {
    render(
      <ResolutionRules resolverType={null} resolutionSource={null} />
    );

    expect(
      screen.queryByText('Resolution Information')
    ).not.toBeInTheDocument();
  });
});

// ============================================================================
// Resolved Status Tests
// ============================================================================

describe('ResolutionRules resolved status', () => {
  it('displays resolved banner when market is resolved', () => {
    render(<ResolutionRules isResolved={true} />);

    expect(screen.getByText('Resolved')).toBeInTheDocument();
  });

  it('displays resolution outcome when provided', () => {
    render(
      <ResolutionRules isResolved={true} resolutionOutcome="Yes" />
    );

    expect(screen.getByText('Resolved')).toBeInTheDocument();
    expect(screen.getByText(/Yes/)).toBeInTheDocument();
  });

  it('does not show resolved banner when not resolved', () => {
    render(<ResolutionRules isResolved={false} />);

    expect(screen.queryByText('Resolved')).not.toBeInTheDocument();
  });

  it('does not show resolved banner by default', () => {
    render(<ResolutionRules description="Some description" />);

    expect(screen.queryByText('Resolved')).not.toBeInTheDocument();
  });
});

// ============================================================================
// Propose Resolution Button Tests
// ============================================================================

describe('ResolutionRules propose resolution button', () => {
  it('shows disabled propose resolution button when not resolved', () => {
    render(<ResolutionRules isResolved={false} />);

    const button = screen.getByRole('button', { name: /Propose Resolution/i });
    expect(button).toBeInTheDocument();
    expect(button).toBeDisabled();
  });

  it('shows coming soon text for propose resolution', () => {
    render(<ResolutionRules isResolved={false} />);

    expect(
      screen.getByText('Resolution proposals coming soon')
    ).toBeInTheDocument();
  });

  it('does not show propose resolution button when resolved', () => {
    render(<ResolutionRules isResolved={true} />);

    expect(
      screen.queryByRole('button', { name: /Propose Resolution/i })
    ).not.toBeInTheDocument();
  });

  it('propose resolution button has correct title tooltip', () => {
    render(<ResolutionRules isResolved={false} />);

    const button = screen.getByRole('button', { name: /Propose Resolution/i });
    expect(button).toHaveAttribute(
      'title',
      'Proposing resolutions is not yet available'
    );
  });
});

// ============================================================================
// Combined Feature Tests
// ============================================================================

describe('ResolutionRules combined features', () => {
  it('renders all features together correctly', () => {
    const description = `This market will resolve based on official election results.

    - Votes must be certified
    - Official announcement required
    - No legal challenges pending`;

    render(
      <ResolutionRules
        description={description}
        resolverType="UMA Optimistic Oracle"
        resolutionSource="Associated Press"
        isResolved={false}
      />
    );

    // Title
    expect(screen.getByText('Resolution Rules')).toBeInTheDocument();

    // Description
    expect(
      screen.getByText(/This market will resolve based on official election results/)
    ).toBeInTheDocument();

    // Criteria
    expect(screen.getByText('Key Resolution Criteria')).toBeInTheDocument();
    expect(screen.getByText('Votes must be certified')).toBeInTheDocument();

    // Resolver info
    expect(screen.getByText('UMA Optimistic Oracle')).toBeInTheDocument();
    expect(screen.getByText('Associated Press')).toBeInTheDocument();

    // Propose button (not resolved)
    expect(
      screen.getByRole('button', { name: /Propose Resolution/i })
    ).toBeDisabled();
  });

  it('renders resolved market correctly', () => {
    render(
      <ResolutionRules
        description="Market description here"
        resolverType="Polymarket"
        isResolved={true}
        resolutionOutcome="No"
      />
    );

    // Resolved banner
    expect(screen.getByText('Resolved')).toBeInTheDocument();
    expect(screen.getByText(/No/)).toBeInTheDocument();

    // No propose button for resolved markets
    expect(
      screen.queryByRole('button', { name: /Propose Resolution/i })
    ).not.toBeInTheDocument();
  });
});
