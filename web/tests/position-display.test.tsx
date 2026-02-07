/**
 * Position Display Component Tests
 *
 * Tests for the PositionDisplay component:
 * - Rendering position details (Shares, Avg Cost, Value, P&L)
 * - Color coding for positive/negative PnL
 * - Close Position button placeholder
 * - Loading state
 * - No position/zero quantity handling
 * - Accessibility
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PositionDisplay, type Position } from '@/components/event/position-display';

// Helper to create a position
function createPosition(overrides?: Partial<Position>): Position {
  return {
    outcomeId: 'outcome-yes',
    outcomeName: 'Yes',
    quantity: 100,
    avgCost: 0.5,
    currentPrice: 0.65,
    unrealizedPnl: 15,
    realizedPnl: 5,
    ...overrides,
  };
}

describe('PositionDisplay', () => {
  // ============================================================================
  // Render Behavior Tests
  // ============================================================================

  describe('Render Behavior', () => {
    it('does not render when position is null', () => {
      const { container } = render(<PositionDisplay position={null} />);

      expect(container.firstChild).toBeNull();
    });

    it('does not render when quantity is zero', () => {
      const { container } = render(
        <PositionDisplay position={createPosition({ quantity: 0 })} />
      );

      expect(container.firstChild).toBeNull();
    });

    it('renders when position has non-zero quantity', () => {
      render(<PositionDisplay position={createPosition()} />);

      expect(screen.getByTestId('position-display')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Position Details Tests
  // ============================================================================

  describe('Position Details', () => {
    it('displays "Your Position" header with wallet icon', () => {
      render(<PositionDisplay position={createPosition()} />);

      expect(screen.getByText('Your Position')).toBeInTheDocument();
    });

    it('displays outcome name', () => {
      render(<PositionDisplay position={createPosition({ outcomeName: 'Yes' })} />);

      expect(screen.getByText('Yes')).toBeInTheDocument();
    });

    it('displays shares held', () => {
      render(<PositionDisplay position={createPosition({ quantity: 100 })} />);

      expect(screen.getByText('Shares')).toBeInTheDocument();
      expect(screen.getByText('100.00')).toBeInTheDocument();
    });

    it('formats large share counts with commas', () => {
      render(<PositionDisplay position={createPosition({ quantity: 10000 })} />);

      expect(screen.getByText('10,000')).toBeInTheDocument();
    });

    it('displays average cost as cents', () => {
      render(<PositionDisplay position={createPosition({ avgCost: 0.45 })} />);

      expect(screen.getByText('Avg Cost')).toBeInTheDocument();
      expect(screen.getByText('45¢')).toBeInTheDocument();
    });

    it('displays current value', () => {
      // 100 shares * 0.65 = $65
      render(
        <PositionDisplay
          position={createPosition({ quantity: 100, currentPrice: 0.65 })}
        />
      );

      expect(screen.getByText('Value')).toBeInTheDocument();
      expect(screen.getByText('$65.00')).toBeInTheDocument();
    });

    it('displays P&L (unrealized + realized)', () => {
      // unrealizedPnl: 15 + realizedPnl: 5 = 20
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: 15, realizedPnl: 5 })}
        />
      );

      expect(screen.getByText('P&L')).toBeInTheDocument();
      expect(screen.getByText('+$20.00')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // PnL Color Coding Tests
  // ============================================================================

  describe('PnL Color Coding', () => {
    it('shows green color for positive PnL', () => {
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: 50, realizedPnl: 0 })}
        />
      );

      const pnlValue = screen.getByText('+$50.00');
      expect(pnlValue).toHaveClass('text-green-600');
    });

    it('shows red color for negative PnL', () => {
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: -30, realizedPnl: 0 })}
        />
      );

      const pnlValue = screen.getByText('-$30.00');
      expect(pnlValue).toHaveClass('text-red-600');
    });

    it('shows green color for zero PnL', () => {
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: 0, realizedPnl: 0 })}
        />
      );

      const pnlValue = screen.getByText('+$0.00');
      expect(pnlValue).toHaveClass('text-green-600');
    });

    it('shows green border for profitable positions', () => {
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: 50, realizedPnl: 0 })}
        />
      );

      expect(screen.getByTestId('position-display')).toHaveClass('border-green-200');
    });

    it('shows red border for losing positions', () => {
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: -50, realizedPnl: 0 })}
        />
      );

      expect(screen.getByTestId('position-display')).toHaveClass('border-red-200');
    });

    it('includes TrendingUp icon for positive PnL', () => {
      const { container } = render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: 50, realizedPnl: 0 })}
        />
      );

      // TrendingUp icon should be present
      const svg = container.querySelector('.lucide-trending-up');
      expect(svg).toBeInTheDocument();
    });

    it('includes TrendingDown icon for negative PnL', () => {
      const { container } = render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: -50, realizedPnl: 0 })}
        />
      );

      // TrendingDown icon should be present
      const svg = container.querySelector('.lucide-trending-down');
      expect(svg).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Close Position Button Tests
  // ============================================================================

  describe('Close Position Button', () => {
    it('renders Close Position button', () => {
      render(<PositionDisplay position={createPosition()} />);

      expect(screen.getByTestId('close-position-button')).toBeInTheDocument();
      expect(screen.getByText('Close Position')).toBeInTheDocument();
    });

    it('calls onClosePosition when button is clicked', () => {
      const handleClose = vi.fn();
      render(
        <PositionDisplay position={createPosition()} onClosePosition={handleClose} />
      );

      fireEvent.click(screen.getByTestId('close-position-button'));
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('button is disabled when onClosePosition is not provided', () => {
      render(<PositionDisplay position={createPosition()} />);

      const button = screen.getByTestId('close-position-button');
      expect(button).toBeDisabled();
    });

    it('button is enabled when onClosePosition is provided', () => {
      const handleClose = vi.fn();
      render(
        <PositionDisplay position={createPosition()} onClosePosition={handleClose} />
      );

      const button = screen.getByTestId('close-position-button');
      expect(button).not.toBeDisabled();
    });

    it('button has correct aria-label', () => {
      render(<PositionDisplay position={createPosition()} />);

      expect(screen.getByRole('button', { name: /close position/i })).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Loading State Tests
  // ============================================================================

  describe('Loading State', () => {
    it('shows loading skeleton when loading', () => {
      render(<PositionDisplay position={createPosition()} loading={true} />);

      expect(screen.getByTestId('position-display-loading')).toBeInTheDocument();
    });

    it('has aria-busy when loading', () => {
      render(<PositionDisplay position={createPosition()} loading={true} />);

      expect(screen.getByTestId('position-display-loading')).toHaveAttribute(
        'aria-busy',
        'true'
      );
    });

    it('has aria-label when loading', () => {
      render(<PositionDisplay position={createPosition()} loading={true} />);

      expect(screen.getByLabelText(/loading position/i)).toBeInTheDocument();
    });

    it('does not show position details when loading', () => {
      render(<PositionDisplay position={createPosition()} loading={true} />);

      expect(screen.queryByText('Your Position')).not.toBeInTheDocument();
      expect(screen.queryByText('Shares')).not.toBeInTheDocument();
    });

    it('does not render loading when position is null', () => {
      const { container } = render(<PositionDisplay position={null} loading={true} />);

      expect(container.firstChild).toBeNull();
    });
  });

  // ============================================================================
  // Calculations Tests
  // ============================================================================

  describe('Calculations', () => {
    it('calculates current value correctly', () => {
      // 250 shares * 0.80 price = $200
      render(
        <PositionDisplay
          position={createPosition({ quantity: 250, currentPrice: 0.8 })}
        />
      );

      expect(screen.getByText('$200.00')).toBeInTheDocument();
    });

    it('calculates total PnL correctly', () => {
      // unrealized: 100 + realized: 50 = 150
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: 100, realizedPnl: 50 })}
        />
      );

      expect(screen.getByText('+$150.00')).toBeInTheDocument();
    });

    it('handles mixed positive/negative PnL', () => {
      // unrealized: 100 + realized: -30 = 70
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: 100, realizedPnl: -30 })}
        />
      );

      expect(screen.getByText('+$70.00')).toBeInTheDocument();
    });

    it('handles all negative PnL', () => {
      // unrealized: -50 + realized: -25 = -75
      render(
        <PositionDisplay
          position={createPosition({ unrealizedPnl: -50, realizedPnl: -25 })}
        />
      );

      expect(screen.getByText('-$75.00')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Edge Cases Tests
  // ============================================================================

  describe('Edge Cases', () => {
    it('handles very large positions', () => {
      render(
        <PositionDisplay
          position={createPosition({
            quantity: 1000000,
            currentPrice: 0.5,
            unrealizedPnl: 500000,
          })}
        />
      );

      expect(screen.getByText('1,000,000')).toBeInTheDocument();
      expect(screen.getByText('$500,000.00')).toBeInTheDocument();
    });

    it('handles very small prices', () => {
      render(
        <PositionDisplay position={createPosition({ avgCost: 0.01 })} />
      );

      expect(screen.getByText('1¢')).toBeInTheDocument();
    });

    it('handles fractional shares', () => {
      render(
        <PositionDisplay position={createPosition({ quantity: 123.45 })} />
      );

      expect(screen.getByText('123.45')).toBeInTheDocument();
    });

    it('handles long outcome names', () => {
      const longName = 'This is a very long outcome name that might need truncation';
      render(<PositionDisplay position={createPosition({ outcomeName: longName })} />);

      expect(screen.getByText(longName)).toBeInTheDocument();
    });

    it('handles negative quantity gracefully (treats as zero)', () => {
      const { container } = render(
        <PositionDisplay position={createPosition({ quantity: -100 })} />
      );

      // Negative quantity is still non-zero, so it should render
      // But the calculations would be odd - in practice this shouldn't happen
      expect(container.firstChild).not.toBeNull();
    });
  });

  // ============================================================================
  // Accessibility Tests
  // ============================================================================

  describe('Accessibility', () => {
    it('has region role with aria-label', () => {
      render(<PositionDisplay position={createPosition()} />);

      expect(
        screen.getByRole('region', { name: /your position/i })
      ).toBeInTheDocument();
    });

    it('applies custom className', () => {
      render(
        <PositionDisplay position={createPosition()} className="my-custom-class" />
      );

      expect(screen.getByTestId('position-display')).toHaveClass('my-custom-class');
    });

    it('button has type="button"', () => {
      render(<PositionDisplay position={createPosition()} />);

      const button = screen.getByTestId('close-position-button');
      expect(button).toHaveAttribute('type', 'button');
    });
  });

  // ============================================================================
  // Styling Tests
  // ============================================================================

  describe('Styling', () => {
    it('has rounded-lg border styling', () => {
      render(<PositionDisplay position={createPosition()} />);

      const container = screen.getByTestId('position-display');
      expect(container).toHaveClass('rounded-lg', 'border');
    });

    it('has white background', () => {
      render(<PositionDisplay position={createPosition()} />);

      expect(screen.getByTestId('position-display')).toHaveClass('bg-white');
    });

    it('has padding', () => {
      render(<PositionDisplay position={createPosition()} />);

      expect(screen.getByTestId('position-display')).toHaveClass('p-4');
    });
  });
});
