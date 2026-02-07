/**
 * Probability Display Component Tests
 *
 * Tests for probability display components:
 * - Helper functions (formatProbability, formatProbabilityAsCents, getProbabilityColor)
 * - ProbabilityBadge component
 * - ProbabilityBar component
 * - LargeProbabilityDisplay component
 * - ProbabilityChange component
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  formatProbability,
  formatProbabilityAsCents,
  getProbabilityColor,
  ProbabilityBadge,
  ProbabilityBar,
  LargeProbabilityDisplay,
  ProbabilityChange,
} from '@/components/event/probability-display';

// ============================================================================
// Helper Function Tests
// ============================================================================

describe('formatProbability', () => {
  it('formats probability as percentage with no decimals by default', () => {
    expect(formatProbability(0.5)).toBe('50%');
    expect(formatProbability(0.12)).toBe('12%');
    expect(formatProbability(1)).toBe('100%');
    expect(formatProbability(0)).toBe('0%');
  });

  it('formats with specified decimal places', () => {
    expect(formatProbability(0.123, 1)).toBe('12.3%');
    expect(formatProbability(0.5678, 2)).toBe('56.78%');
    expect(formatProbability(0.1, 2)).toBe('10.00%');
  });

  it('rounds correctly', () => {
    expect(formatProbability(0.125)).toBe('13%');
    expect(formatProbability(0.124)).toBe('12%');
  });
});

describe('formatProbabilityAsCents', () => {
  it('formats probability as cents', () => {
    expect(formatProbabilityAsCents(0.12)).toBe('12¢');
    expect(formatProbabilityAsCents(0.5)).toBe('50¢');
    expect(formatProbabilityAsCents(1)).toBe('100¢');
    expect(formatProbabilityAsCents(0)).toBe('0¢');
  });

  it('rounds to nearest cent', () => {
    expect(formatProbabilityAsCents(0.125)).toBe('13¢');
    expect(formatProbabilityAsCents(0.124)).toBe('12¢');
    expect(formatProbabilityAsCents(0.999)).toBe('100¢');
  });
});

describe('getProbabilityColor', () => {
  it('returns green colors for high probability (>=70%)', () => {
    const colors = getProbabilityColor(0.7);
    expect(colors.bg).toBe('bg-green-50');
    expect(colors.text).toBe('text-green-700');
    expect(colors.barColor).toBe('bg-green-500');
  });

  it('returns emerald colors for medium-high probability (50-69%)', () => {
    const colors = getProbabilityColor(0.5);
    expect(colors.bg).toBe('bg-emerald-50');
    expect(colors.text).toBe('text-emerald-700');
    expect(colors.barColor).toBe('bg-emerald-500');
  });

  it('returns yellow colors for medium probability (30-49%)', () => {
    const colors = getProbabilityColor(0.3);
    expect(colors.bg).toBe('bg-yellow-50');
    expect(colors.text).toBe('text-yellow-700');
    expect(colors.barColor).toBe('bg-yellow-500');
  });

  it('returns orange colors for low-medium probability (15-29%)', () => {
    const colors = getProbabilityColor(0.15);
    expect(colors.bg).toBe('bg-orange-50');
    expect(colors.text).toBe('text-orange-700');
    expect(colors.barColor).toBe('bg-orange-500');
  });

  it('returns red colors for low probability (<15%)', () => {
    const colors = getProbabilityColor(0.1);
    expect(colors.bg).toBe('bg-red-50');
    expect(colors.text).toBe('text-red-700');
    expect(colors.barColor).toBe('bg-red-500');
  });

  it('handles edge cases', () => {
    expect(getProbabilityColor(0).bg).toBe('bg-red-50');
    expect(getProbabilityColor(1).bg).toBe('bg-green-50');
  });
});

// ============================================================================
// ProbabilityBadge Tests
// ============================================================================

describe('ProbabilityBadge', () => {
  it('renders probability as percentage', () => {
    render(<ProbabilityBadge value={0.5} />);
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('renders probability as cents when showAsCents is true', () => {
    render(<ProbabilityBadge value={0.25} showAsCents />);
    expect(screen.getByText('25¢')).toBeInTheDocument();
  });

  it('renders with specified decimals', () => {
    render(<ProbabilityBadge value={0.125} decimals={1} />);
    expect(screen.getByText('12.5%')).toBeInTheDocument();
  });

  it('applies color classes based on probability', () => {
    const { container } = render(<ProbabilityBadge value={0.75} />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('bg-green-50');
    expect(badge).toHaveClass('text-green-700');
  });

  it('renders small size', () => {
    const { container } = render(<ProbabilityBadge value={0.5} size="sm" />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('text-xs');
    expect(badge).toHaveClass('px-1.5');
  });

  it('renders medium size (default)', () => {
    const { container } = render(<ProbabilityBadge value={0.5} />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('text-sm');
    expect(badge).toHaveClass('px-2');
  });

  it('renders large size', () => {
    const { container } = render(<ProbabilityBadge value={0.5} size="lg" />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('text-base');
    expect(badge).toHaveClass('px-3');
  });

  it('accepts custom className', () => {
    const { container } = render(<ProbabilityBadge value={0.5} className="my-custom-class" />);
    const badge = container.firstChild;
    expect(badge).toHaveClass('my-custom-class');
  });
});

// ============================================================================
// ProbabilityBar Tests
// ============================================================================

describe('ProbabilityBar', () => {
  it('renders bar with correct width based on probability', () => {
    const { container } = render(<ProbabilityBar value={0.6} animated={false} />);
    const bar = container.querySelector('.bg-emerald-500');
    expect(bar).toHaveStyle({ width: '60%' });
  });

  it('applies color based on probability', () => {
    const { container } = render(<ProbabilityBar value={0.8} animated={false} />);
    const bar = container.querySelector('.bg-green-500');
    expect(bar).toBeInTheDocument();
  });

  it('renders different heights', () => {
    const { container: xsContainer } = render(
      <ProbabilityBar value={0.5} height="xs" animated={false} />
    );
    expect(xsContainer.querySelector('.h-1')).toBeInTheDocument();

    const { container: lgContainer } = render(
      <ProbabilityBar value={0.5} height="lg" animated={false} />
    );
    expect(lgContainer.querySelector('.h-4')).toBeInTheDocument();
  });

  it('shows label on the right when showLabel and labelPosition=right', () => {
    render(<ProbabilityBar value={0.5} showLabel labelPosition="right" animated={false} />);
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('accepts custom className', () => {
    const { container } = render(
      <ProbabilityBar value={0.5} className="my-custom-class" animated={false} />
    );
    expect(container.firstChild).toHaveClass('my-custom-class');
  });

  it('applies transition classes when animated', () => {
    const { container } = render(<ProbabilityBar value={0.5} animated />);
    const bar = container.querySelector('[class*="transition-all"]');
    expect(bar).toBeInTheDocument();
  });
});

// ============================================================================
// LargeProbabilityDisplay Tests
// ============================================================================

describe('LargeProbabilityDisplay', () => {
  it('renders probability as large percentage', () => {
    render(<LargeProbabilityDisplay value={0.42} />);
    expect(screen.getByText('42%')).toBeInTheDocument();
  });

  it('renders with label', () => {
    render(<LargeProbabilityDisplay value={0.5} label="Yes" />);
    expect(screen.getByText('Yes')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('renders with chance suffix', () => {
    render(<LargeProbabilityDisplay value={0.5} showChanceSuffix />);
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('chance')).toBeInTheDocument();
  });

  it('applies color based on probability', () => {
    render(<LargeProbabilityDisplay value={0.8} />);
    const percentage = screen.getByText('80%');
    expect(percentage).toHaveClass('text-green-700');
  });

  it('accepts custom className', () => {
    const { container } = render(
      <LargeProbabilityDisplay value={0.5} className="my-custom-class" />
    );
    expect(container.firstChild).toHaveClass('my-custom-class');
  });
});

// ============================================================================
// ProbabilityChange Tests
// ============================================================================

describe('ProbabilityChange', () => {
  it('renders positive change with up arrow and green color', () => {
    render(<ProbabilityChange change={0.05} />);
    expect(screen.getByText('↑')).toBeInTheDocument();
    expect(screen.getByText('5.0%')).toBeInTheDocument();
    expect(screen.getByText('↑').parentElement).toHaveClass('text-green-600');
  });

  it('renders negative change with down arrow and red color', () => {
    render(<ProbabilityChange change={-0.03} />);
    expect(screen.getByText('↓')).toBeInTheDocument();
    expect(screen.getByText('3.0%')).toBeInTheDocument();
    expect(screen.getByText('↓').parentElement).toHaveClass('text-red-600');
  });

  it('renders zero change with gray color', () => {
    render(<ProbabilityChange change={0} />);
    expect(screen.getByText('0%')).toBeInTheDocument();
    expect(screen.getByText('0%')).toHaveClass('text-gray-500');
  });

  it('renders small size', () => {
    render(<ProbabilityChange change={0.05} size="sm" />);
    expect(screen.getByText('↑').parentElement).toHaveClass('text-xs');
  });

  it('renders medium size (default)', () => {
    render(<ProbabilityChange change={0.05} />);
    expect(screen.getByText('↑').parentElement).toHaveClass('text-sm');
  });

  it('accepts custom className', () => {
    render(<ProbabilityChange change={0.05} className="my-custom-class" />);
    expect(screen.getByText('↑').parentElement).toHaveClass('my-custom-class');
  });
});
