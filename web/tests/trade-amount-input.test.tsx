/**
 * Trade Amount Input Component Tests
 *
 * Tests for the TradeAmountInput component:
 * - Rendering input and quick amount buttons
 * - Input validation (min $1, max based on liquidity)
 * - Shares calculation based on price
 * - Potential payout and ROI display
 * - Quick amount button selection
 * - Disabled state
 * - Error handling
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TradeAmountInput } from '@/components/event/trade-amount-input';

describe('TradeAmountInput', () => {
  // ============================================================================
  // Rendering Tests
  // ============================================================================

  describe('Rendering', () => {
    it('renders amount input with USD prefix', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      expect(screen.getByLabelText(/trade amount/i)).toBeInTheDocument();
      expect(screen.getByText('$')).toBeInTheDocument();
    });

    it('renders "Amount" label', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      expect(screen.getByText('Amount')).toBeInTheDocument();
    });

    it('renders quick amount buttons', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      expect(screen.getByRole('button', { name: '$10' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '$50' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '$100' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '$500' })).toBeInTheDocument();
    });

    it('displays initial amount value in input', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={100} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      expect(input).toHaveValue('100');
    });

    it('applies custom className', () => {
      const onChange = vi.fn();
      const { container } = render(
        <TradeAmountInput
          amount={null}
          onAmountChange={onChange}
          price={0.5}
          className="my-custom-class"
        />
      );

      expect(container.querySelector('.my-custom-class')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Input Handling Tests
  // ============================================================================

  describe('Input Handling', () => {
    it('calls onAmountChange when valid amount is entered', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.type(input, '50');

      expect(onChange).toHaveBeenCalledWith(50);
    });

    it('allows decimal amounts', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.type(input, '25.50');

      expect(onChange).toHaveBeenCalledWith(25.5);
    });

    it('rejects non-numeric input', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.type(input, 'abc');

      expect(input).toHaveValue('');
    });

    it('calls onAmountChange with null when input is cleared', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.clear(input);

      expect(onChange).toHaveBeenCalledWith(null);
    });
  });

  // ============================================================================
  // Validation Tests
  // ============================================================================

  describe('Validation', () => {
    it('shows error for amount below minimum ($1)', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.type(input, '0.50');

      expect(screen.getByRole('alert')).toHaveTextContent(/minimum amount/i);
      expect(onChange).toHaveBeenLastCalledWith(null);
    });

    it('shows error for amount above maximum', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput
          amount={null}
          onAmountChange={onChange}
          price={0.5}
          maxAmount={100}
        />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.type(input, '150');

      expect(screen.getByRole('alert')).toHaveTextContent(/maximum amount/i);
      expect(onChange).toHaveBeenLastCalledWith(null);
    });

    it('clears error when valid amount is entered', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);

      // Enter invalid amount first
      await user.type(input, '0.5');
      expect(screen.getByRole('alert')).toBeInTheDocument();

      // Clear and enter valid amount
      await user.clear(input);
      await user.type(input, '50');

      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('marks input as aria-invalid when there is an error', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.type(input, '0.5');

      expect(input).toHaveAttribute('aria-invalid', 'true');
    });
  });

  // ============================================================================
  // Quick Amount Button Tests
  // ============================================================================

  describe('Quick Amount Buttons', () => {
    it('sets amount when quick amount button is clicked', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      await user.click(screen.getByRole('button', { name: '$50' }));

      expect(onChange).toHaveBeenCalledWith(50);
    });

    it('highlights selected quick amount button', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={0.5} />
      );

      const button = screen.getByRole('button', { name: '$50' });
      expect(button).toHaveAttribute('aria-pressed', 'true');
      expect(button).toHaveClass('bg-indigo-100');
    });

    it('disables quick amount buttons above maxAmount', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput
          amount={null}
          onAmountChange={onChange}
          price={0.5}
          maxAmount={75}
        />
      );

      expect(screen.getByRole('button', { name: '$10' })).not.toBeDisabled();
      expect(screen.getByRole('button', { name: '$50' })).not.toBeDisabled();
      expect(screen.getByRole('button', { name: '$100' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '$500' })).toBeDisabled();
    });

    it('updates input value when quick amount is selected', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      await user.click(screen.getByRole('button', { name: '$100' }));

      const input = screen.getByLabelText(/trade amount/i);
      expect(input).toHaveValue('100');
    });
  });

  // ============================================================================
  // Calculations Tests
  // ============================================================================

  describe('Calculations', () => {
    it('shows shares calculation for valid amount', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={0.5} />
      );

      // $50 at 50¢ = 100 shares
      expect(screen.getByText('Shares')).toBeInTheDocument();
      expect(screen.getByText('100.00')).toBeInTheDocument();
    });

    it('shows potential payout', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={0.5} />
      );

      // 100 shares * $1 = $100 payout
      expect(screen.getByText('Potential payout')).toBeInTheDocument();
      expect(screen.getByText('$100.00')).toBeInTheDocument();
    });

    it('shows ROI percentage', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={0.5} />
      );

      // ($100 - $50) / $50 * 100 = 100%
      expect(screen.getByText('Potential return')).toBeInTheDocument();
      expect(screen.getByText('+100.0%')).toBeInTheDocument();
    });

    it('calculates correctly for different prices', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={10} onAmountChange={onChange} price={0.1} />
      );

      // $10 at 10¢ = 100 shares
      expect(screen.getByText('100.00')).toBeInTheDocument();
      // 100 shares * $1 = $100 payout
      expect(screen.getByText('$100.00')).toBeInTheDocument();
      // ($100 - $10) / $10 * 100 = 900%
      expect(screen.getByText('+900.0%')).toBeInTheDocument();
    });

    it('does not show calculations when no amount is entered', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      expect(screen.queryByText('Shares')).not.toBeInTheDocument();
      expect(screen.queryByText('Potential payout')).not.toBeInTheDocument();
    });

    it('does not show calculations for invalid price', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={0} />
      );

      expect(screen.queryByText('Shares')).not.toBeInTheDocument();
    });
  });

  // ============================================================================
  // Disabled State Tests
  // ============================================================================

  describe('Disabled State', () => {
    it('disables input when disabled prop is true', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput
          amount={null}
          onAmountChange={onChange}
          price={0.5}
          disabled
        />
      );

      expect(screen.getByLabelText(/trade amount/i)).toBeDisabled();
    });

    it('disables quick amount buttons when disabled', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput
          amount={null}
          onAmountChange={onChange}
          price={0.5}
          disabled
        />
      );

      expect(screen.getByRole('button', { name: '$10' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '$50' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '$100' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '$500' })).toBeDisabled();
    });

    it('does not call onAmountChange when clicking quick amount while disabled', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput
          amount={null}
          onAmountChange={onChange}
          price={0.5}
          disabled
        />
      );

      await user.click(screen.getByRole('button', { name: '$50' }));

      expect(onChange).not.toHaveBeenCalled();
    });

    it('applies disabled styling to input', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput
          amount={null}
          onAmountChange={onChange}
          price={0.5}
          disabled
        />
      );

      const input = screen.getByLabelText(/trade amount/i);
      expect(input).toHaveClass('opacity-50');
      expect(input).toHaveClass('cursor-not-allowed');
    });
  });

  // ============================================================================
  // Accessibility Tests
  // ============================================================================

  describe('Accessibility', () => {
    it('has accessible input label', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      expect(screen.getByLabelText(/trade amount/i)).toBeInTheDocument();
    });

    it('has aria-describedby pointing to error when invalid', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.type(input, '0.5');

      expect(input).toHaveAttribute('aria-describedby', 'amount-error');
    });

    it('error message has alert role', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      await user.type(input, '0.5');

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('quick amount buttons have aria-pressed attribute', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={0.5} />
      );

      expect(screen.getByRole('button', { name: '$50' })).toHaveAttribute(
        'aria-pressed',
        'true'
      );
      expect(screen.getByRole('button', { name: '$10' })).toHaveAttribute(
        'aria-pressed',
        'false'
      );
    });

    it('uses decimal input mode for mobile keyboards', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={null} onAmountChange={onChange} price={0.5} />
      );

      const input = screen.getByLabelText(/trade amount/i);
      expect(input).toHaveAttribute('inputMode', 'decimal');
    });
  });

  // ============================================================================
  // Edge Cases
  // ============================================================================

  describe('Edge Cases', () => {
    it('handles price at boundary 1.0 (no shares)', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={1.0} />
      );

      // At price 1.0, should not show calculations (no profit possible)
      expect(screen.queryByText('Shares')).not.toBeInTheDocument();
    });

    it('handles very small price', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput amount={10} onAmountChange={onChange} price={0.01} />
      );

      // $10 at 1¢ = 1000 shares (formatted with commas)
      expect(screen.getByText('1,000')).toBeInTheDocument();
    });

    it('handles large amounts', () => {
      const onChange = vi.fn();
      render(
        <TradeAmountInput
          amount={5000}
          onAmountChange={onChange}
          price={0.5}
          maxAmount={10000}
        />
      );

      // $5000 at 50¢ = 10000 shares
      expect(screen.getByText('10,000')).toBeInTheDocument();
    });

    it('syncs input value when amount prop changes externally', () => {
      const onChange = vi.fn();
      const { rerender } = render(
        <TradeAmountInput amount={50} onAmountChange={onChange} price={0.5} />
      );

      // Verify initial value
      expect(screen.getByLabelText(/trade amount/i)).toHaveValue('50');

      // Update amount externally
      rerender(
        <TradeAmountInput amount={100} onAmountChange={onChange} price={0.5} />
      );

      expect(screen.getByLabelText(/trade amount/i)).toHaveValue('100');
    });
  });
});
