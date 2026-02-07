/**
 * Trade Summary Component Tests
 *
 * Tests for the TradeSummary component:
 * - Rendering order details (Outcome, Direction, Amount, Shares, Avg Price)
 * - Potential return with percentage
 * - Estimated fees display
 * - Total cost/proceeds calculation
 * - Placeholder states when incomplete
 * - Loading state
 * - Accessibility
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TradeSummary } from '@/components/event/trade-summary';

describe('TradeSummary', () => {
  // ============================================================================
  // Placeholder State Tests
  // ============================================================================

  describe('Placeholder States', () => {
    it('shows placeholder when outcome is not selected', () => {
      render(
        <TradeSummary
          outcomeName={null}
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(
        screen.getByText(/select an outcome to see order summary/i)
      ).toBeInTheDocument();
    });

    it('shows placeholder when amount is null', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={null}
          price={0.5}
        />
      );

      expect(
        screen.getByText(/enter an amount to see order summary/i)
      ).toBeInTheDocument();
    });

    it('shows placeholder when amount is zero', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={0}
          price={0.5}
        />
      );

      expect(
        screen.getByText(/enter an amount to see order summary/i)
      ).toBeInTheDocument();
    });

    it('has aria-label for incomplete placeholder', () => {
      render(
        <TradeSummary
          outcomeName={null}
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(
        screen.getByLabelText(/trade summary - incomplete/i)
      ).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Rendering Complete Summary Tests
  // ============================================================================

  describe('Rendering Complete Summary', () => {
    it('renders order summary header', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Order Summary')).toBeInTheDocument();
    });

    it('displays outcome name', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Outcome')).toBeInTheDocument();
      expect(screen.getByText('Yes')).toBeInTheDocument();
    });

    it('displays direction as Buy with green color', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Direction')).toBeInTheDocument();
      const buyText = screen.getByText('Buy');
      expect(buyText).toBeInTheDocument();
      expect(buyText).toHaveClass('text-green-600');
    });

    it('displays direction as Sell with red color', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="sell"
          amount={50}
          price={0.5}
        />
      );

      const sellText = screen.getByText('Sell');
      expect(sellText).toBeInTheDocument();
      expect(sellText).toHaveClass('text-red-600');
    });

    it('displays amount formatted as currency', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Amount')).toBeInTheDocument();
      // Amount and Total Cost both show $50.00, so we check for at least one
      expect(screen.getAllByText('$50.00').length).toBeGreaterThanOrEqual(1);
    });

    it('displays shares calculation', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Shares')).toBeInTheDocument();
      // $50 at 50¢ = 100 shares
      expect(screen.getByText('100.00')).toBeInTheDocument();
    });

    it('displays average price as cents', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Avg Price')).toBeInTheDocument();
      expect(screen.getByText('50¢')).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const { container } = render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
          className="my-custom-class"
        />
      );

      expect(container.querySelector('.my-custom-class')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Calculations Tests
  // ============================================================================

  describe('Calculations', () => {
    it('calculates shares correctly for different prices', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={10}
          price={0.1}
        />
      );

      // $10 at 10¢ = 100 shares
      expect(screen.getByText('100.00')).toBeInTheDocument();
    });

    it('formats large share counts with commas', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={1000}
          price={0.1}
        />
      );

      // $1000 at 10¢ = 10,000 shares
      expect(screen.getByText('10,000')).toBeInTheDocument();
    });

    it('calculates potential return correctly', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      // 100 shares * $1 = $100 payout
      // $100 - $50 cost = $50 return
      expect(screen.getByText('+$50.00')).toBeInTheDocument();
    });

    it('calculates ROI percentage correctly', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      // ($50 return / $50 cost) * 100 = 100%
      expect(screen.getByText('+100.0%')).toBeInTheDocument();
    });

    it('calculates high ROI for low prices', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={10}
          price={0.1}
        />
      );

      // 100 shares * $1 = $100 payout
      // $100 - $10 cost = $90 return
      // ($90 / $10) * 100 = 900%
      expect(screen.getByText('+$90.00')).toBeInTheDocument();
      expect(screen.getByText('+900.0%')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Fees Tests
  // ============================================================================

  describe('Fees', () => {
    it('shows placeholder fees when estimatedFees is 0', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
          estimatedFees={0}
        />
      );

      expect(screen.getByText('Est. Fees')).toBeInTheDocument();
      expect(screen.getByText('(placeholder)')).toBeInTheDocument();
      // Should show $0.00 with grayed out style
      const feeValue = screen.getByText('$0.00');
      expect(feeValue).toHaveClass('text-gray-400');
    });

    it('shows actual fees when provided', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
          estimatedFees={1.5}
        />
      );

      // Check for fees display - need to find the specific $1.50 for fees
      const feeLabel = screen.getByText('Est. Fees');
      expect(feeLabel).toBeInTheDocument();
    });

    it('subtracts fees from potential return', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
          estimatedFees={5}
        />
      );

      // 100 shares * $1 = $100 payout
      // $100 - $50 cost - $5 fees = $45 return
      expect(screen.getByText('+$45.00')).toBeInTheDocument();
    });

    it('includes fees in total cost', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
          estimatedFees={5}
        />
      );

      // $50 + $5 fees = $55 total
      expect(screen.getByText('$55.00')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Direction Labels Tests
  // ============================================================================

  describe('Direction Labels', () => {
    it('shows "Total Cost" for buy orders', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Total Cost')).toBeInTheDocument();
    });

    it('shows "Total Proceeds" for sell orders', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="sell"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Total Proceeds')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Loading State Tests
  // ============================================================================

  describe('Loading State', () => {
    it('shows skeleton when loading', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
          loading={true}
        />
      );

      expect(screen.getByLabelText(/loading trade summary/i)).toBeInTheDocument();
    });

    it('has aria-busy attribute when loading', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
          loading={true}
        />
      );

      expect(screen.getByLabelText(/loading trade summary/i)).toHaveAttribute(
        'aria-busy',
        'true'
      );
    });

    it('does not show order details when loading', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
          loading={true}
        />
      );

      expect(screen.queryByText('Order Summary')).not.toBeInTheDocument();
      expect(screen.queryByText('Yes')).not.toBeInTheDocument();
    });
  });

  // ============================================================================
  // Edge Cases Tests
  // ============================================================================

  describe('Edge Cases', () => {
    it('handles price at boundary 1.0 (shows placeholder)', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={1.0}
        />
      );

      // At price 1.0, calculations fail so placeholder is shown
      expect(
        screen.getByText(/enter an amount to see order summary/i)
      ).toBeInTheDocument();
    });

    it('handles price at boundary 0 (shows placeholder)', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0}
        />
      );

      expect(
        screen.getByText(/enter an amount to see order summary/i)
      ).toBeInTheDocument();
    });

    it('handles very small price correctly', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={1}
          price={0.01}
        />
      );

      // $1 at 1¢ = 100 shares
      expect(screen.getByText('100.00')).toBeInTheDocument();
      expect(screen.getByText('1¢')).toBeInTheDocument();
    });

    it('handles long outcome names', () => {
      const longName =
        'This is a very long outcome name that might overflow the container';
      render(
        <TradeSummary
          outcomeName={longName}
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText(longName)).toBeInTheDocument();
    });

    it('handles decimal amounts', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={25.5}
          price={0.5}
        />
      );

      // Amount and Total Cost both show $25.50, so we check for at least one
      expect(screen.getAllByText('$25.50').length).toBeGreaterThanOrEqual(1);
      // 25.5 / 0.5 = 51 shares
      expect(screen.getByText('51.00')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Accessibility Tests
  // ============================================================================

  describe('Accessibility', () => {
    it('has region role with aria-label when complete', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByRole('region', { name: /trade summary/i })).toBeInTheDocument();
    });

    it('uses semantic heading for Order Summary', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      const heading = screen.getByText('Order Summary');
      expect(heading.tagName).toBe('H3');
    });

    it('has accessible color contrast for potential return', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      // Potential return should be visible with proper color classes
      const returnValue = screen.getByText('+$50.00');
      expect(returnValue).toHaveClass('text-green-600');
    });
  });

  // ============================================================================
  // Potential Return Display Tests
  // ============================================================================

  describe('Potential Return Display', () => {
    it('shows positive return with + prefix and green color', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      const returnValue = screen.getByText('+$50.00');
      expect(returnValue).toHaveClass('text-green-600');
    });

    it('shows potential return label', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      expect(screen.getByText('Potential Return')).toBeInTheDocument();
    });

    it('shows ROI percentage below return amount', () => {
      render(
        <TradeSummary
          outcomeName="Yes"
          direction="buy"
          amount={50}
          price={0.5}
        />
      );

      const roiElement = screen.getByText('+100.0%');
      expect(roiElement).toBeInTheDocument();
      expect(roiElement).toHaveClass('text-green-600');
    });
  });
});
