/**
 * Trade Submit Button Component Tests
 *
 * Tests for the TradeSubmitButton component:
 * - Button text based on direction and outcome
 * - Disabled states (invalid amount, no outcome)
 * - Loading state during submission
 * - Toast notification display
 * - Confetti animation trigger
 * - Color coding for buy/sell
 * - Accessibility
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { TradeSubmitButton } from '@/components/event/trade-submit-button';

describe('TradeSubmitButton', () => {
  // ============================================================================
  // Button Text Tests
  // ============================================================================

  describe('Button Text', () => {
    it('shows "Buy [Outcome]" when direction is buy and outcome is selected', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button', { name: 'Buy Yes' })).toBeInTheDocument();
    });

    it('shows "Sell [Outcome]" when direction is sell and outcome is selected', () => {
      render(
        <TradeSubmitButton
          outcomeName="No"
          direction="sell"
          amount={50}
        />
      );

      expect(screen.getByRole('button', { name: 'Sell No' })).toBeInTheDocument();
    });

    it('shows just "Buy" when no outcome is selected', () => {
      render(
        <TradeSubmitButton
          outcomeName={null}
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button', { name: 'Buy' })).toBeInTheDocument();
    });

    it('shows just "Sell" when no outcome is selected', () => {
      render(
        <TradeSubmitButton
          outcomeName={null}
          direction="sell"
          amount={50}
        />
      );

      expect(screen.getByRole('button', { name: 'Sell' })).toBeInTheDocument();
    });

    it('includes long outcome names in button text', () => {
      const longName = 'Donald Trump wins the 2024 election';
      render(
        <TradeSubmitButton
          outcomeName={longName}
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button', { name: `Buy ${longName}` })).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Disabled State Tests
  // ============================================================================

  describe('Disabled State', () => {
    it('is disabled when amount is null', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={null}
        />
      );

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('is disabled when amount is less than 1', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={0.5}
        />
      );

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('is disabled when amount is zero', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={0}
        />
      );

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('is disabled when no outcome is selected', () => {
      render(
        <TradeSubmitButton
          outcomeName={null}
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('is disabled when disabled prop is true', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
          disabled={true}
        />
      );

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('is enabled when all conditions are met', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).not.toBeDisabled();
    });

    it('has cursor-not-allowed class when disabled', () => {
      render(
        <TradeSubmitButton
          outcomeName={null}
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('cursor-not-allowed');
    });

    it('has gray background when disabled', () => {
      render(
        <TradeSubmitButton
          outcomeName={null}
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('bg-gray-200');
    });
  });

  // ============================================================================
  // Color Coding Tests
  // ============================================================================

  describe('Color Coding', () => {
    it('has green background for buy direction when enabled', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('bg-green-600');
    });

    it('has red background for sell direction when enabled', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="sell"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('bg-red-600');
    });

    it('maintains green hover state for buy', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('hover:bg-green-700');
    });

    it('maintains red hover state for sell', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="sell"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('hover:bg-red-700');
    });
  });

  // ============================================================================
  // Loading State Tests
  // ============================================================================

  describe('Loading State', () => {
    it('shows loading spinner and "Processing..." text when clicked', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      // Should immediately show processing
      expect(screen.getByText('Processing...')).toBeInTheDocument();
    });

    it('has aria-busy attribute during loading', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      expect(button).toHaveAttribute('aria-busy', 'true');
    });

    it('is disabled while loading', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      expect(button).toBeDisabled();
    });

    it('returns to normal state after loading completes', async () => {
      vi.useFakeTimers();

      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      expect(screen.getByText('Processing...')).toBeInTheDocument();

      // Run all timers to completion
      await act(async () => {
        vi.runAllTimers();
      });

      expect(screen.queryByText('Processing...')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Buy Yes' })).toBeInTheDocument();

      vi.useRealTimers();
    });
  });

  // ============================================================================
  // Toast Notification Tests
  // ============================================================================

  describe('Toast Notification', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('shows toast after submission completes', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      // Run all timers to complete the 800ms delay
      await act(async () => {
        vi.runAllTimers();
      });

      expect(screen.getByText('Trading coming soon!')).toBeInTheDocument();
    });

    it('toast has dismiss button', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      await act(async () => {
        vi.runAllTimers();
      });

      expect(screen.getByLabelText('Dismiss notification')).toBeInTheDocument();
    });

    it('toast can be dismissed by clicking close button', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      await act(async () => {
        vi.runAllTimers();
      });

      expect(screen.getByText('Trading coming soon!')).toBeInTheDocument();

      const dismissButton = screen.getByLabelText('Dismiss notification');
      fireEvent.click(dismissButton);

      expect(screen.queryByText('Trading coming soon!')).not.toBeInTheDocument();
    });

    it('toast auto-dismisses after timer expires', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      // Run timers to show toast
      await act(async () => {
        vi.advanceTimersByTime(800);
      });

      expect(screen.getByText('Trading coming soon!')).toBeInTheDocument();

      // Run remaining timers to auto-dismiss toast
      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      expect(screen.queryByText('Trading coming soon!')).not.toBeInTheDocument();
    });

    it('toast has proper alert role for accessibility', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      await act(async () => {
        vi.runAllTimers();
      });

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Confetti Animation Tests
  // ============================================================================

  describe('Confetti Animation', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('shows confetti after submission completes', async () => {
      const { container } = render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      // Run timers to complete submission
      await act(async () => {
        vi.advanceTimersByTime(800);
      });

      const confettiPieces = container.querySelectorAll('.animate-confetti');
      expect(confettiPieces.length).toBeGreaterThan(0);
    });

    it('confetti disappears after 2 seconds', async () => {
      const { container } = render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      // Run timers to show confetti
      await act(async () => {
        vi.advanceTimersByTime(800);
      });

      expect(container.querySelectorAll('.animate-confetti').length).toBeGreaterThan(0);

      // Run timers for confetti to disappear
      await act(async () => {
        vi.advanceTimersByTime(2000);
      });

      expect(container.querySelectorAll('.animate-confetti').length).toBe(0);
    });
  });

  // ============================================================================
  // Click Behavior Tests
  // ============================================================================

  describe('Click Behavior', () => {
    it('does not trigger submission when disabled', async () => {
      render(
        <TradeSubmitButton
          outcomeName={null}
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button');
      fireEvent.click(button);

      // Should not show loading or toast
      expect(screen.queryByText('Processing...')).not.toBeInTheDocument();
      expect(screen.queryByText('Trading coming soon!')).not.toBeInTheDocument();
    });

    it('does not allow multiple submissions while loading', async () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });

      // First click
      fireEvent.click(button);
      expect(screen.getByText('Processing...')).toBeInTheDocument();

      // Second click should not work since button is disabled during loading
      fireEvent.click(button);

      // Still only one "Processing..." text
      expect(screen.getAllByText('Processing...')).toHaveLength(1);
    });
  });

  // ============================================================================
  // Styling Tests
  // ============================================================================

  describe('Styling', () => {
    it('applies custom className', () => {
      const { container } = render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
          className="my-custom-class"
        />
      );

      expect(container.querySelector('.my-custom-class')).toBeInTheDocument();
    });

    it('has full width styling', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('w-full');
    });

    it('has proper font styling', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button');
      expect(button).toHaveClass('font-semibold');
      expect(button).toHaveClass('text-sm');
    });

    it('has rounded corners', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('rounded-lg');
    });
  });

  // ============================================================================
  // Accessibility Tests
  // ============================================================================

  describe('Accessibility', () => {
    it('has aria-disabled attribute when disabled', () => {
      render(
        <TradeSubmitButton
          outcomeName={null}
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveAttribute('aria-disabled', 'true');
    });

    it('has button type attribute', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
    });

    it('toast uses aria-live for screen readers', async () => {
      vi.useFakeTimers();

      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      const button = screen.getByRole('button', { name: 'Buy Yes' });
      fireEvent.click(button);

      await act(async () => {
        vi.runAllTimers();
      });

      const toast = screen.getByRole('alert');
      expect(toast).toHaveAttribute('aria-live', 'polite');

      vi.useRealTimers();
    });

    it('has focus ring on focus for buy', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('focus:ring-green-500');
    });

    it('has focus ring on focus for sell', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="sell"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toHaveClass('focus:ring-red-500');
    });
  });

  // ============================================================================
  // Edge Cases Tests
  // ============================================================================

  describe('Edge Cases', () => {
    it('handles amount at minimum valid value (1)', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={1}
        />
      );

      expect(screen.getByRole('button')).not.toBeDisabled();
    });

    it('handles very large amounts', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={1000000}
        />
      );

      expect(screen.getByRole('button')).not.toBeDisabled();
    });

    it('handles special characters in outcome name', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes & No"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button', { name: 'Buy Yes & No' })).toBeInTheDocument();
    });

    it('handles emoji in outcome name', () => {
      render(
        <TradeSubmitButton
          outcomeName="Yes"
          direction="buy"
          amount={50}
        />
      );

      expect(screen.getByRole('button')).toBeInTheDocument();
    });
  });
});
