/**
 * Trade Direction Toggle Component Tests
 *
 * Tests for the TradeDirectionToggle component:
 * - Rendering buy/sell buttons
 * - Selection behavior
 * - Keyboard shortcuts (B for Buy, S for Sell)
 * - Arrow key navigation
 * - Disabled state
 * - Accessibility attributes
 * - Color coding (green for buy, red for sell)
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TradeDirectionToggle } from '@/components/event/trade-direction-toggle';

describe('TradeDirectionToggle', () => {
  // ============================================================================
  // Rendering Tests
  // ============================================================================

  describe('Rendering', () => {
    it('renders Buy and Sell buttons', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      expect(screen.getByRole('radio', { name: /Buy/i })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /Sell/i })).toBeInTheDocument();
    });

    it('renders "Trade Direction" label', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      expect(screen.getByText('Trade Direction')).toBeInTheDocument();
    });

    it('shows keyboard shortcut hints', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      // Check that keyboard hints are present
      expect(screen.getByText('B')).toBeInTheDocument();
      expect(screen.getByText('S')).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const onChange = vi.fn();
      const { container } = render(
        <TradeDirectionToggle
          direction="buy"
          onDirectionChange={onChange}
          className="my-custom-class"
        />
      );

      expect(container.querySelector('.my-custom-class')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Selection Tests
  // ============================================================================

  describe('Selection', () => {
    it('calls onDirectionChange when Buy is clicked', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="sell" onDirectionChange={onChange} />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      await user.click(buyButton);

      expect(onChange).toHaveBeenCalledWith('buy');
    });

    it('calls onDirectionChange when Sell is clicked', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const sellButton = screen.getByRole('radio', { name: /Sell/i });
      await user.click(sellButton);

      expect(onChange).toHaveBeenCalledWith('sell');
    });

    it('shows Buy as selected with green styling when direction is buy', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      expect(buyButton).toHaveAttribute('aria-checked', 'true');
      expect(buyButton).toHaveClass('bg-green-500');
      expect(buyButton).toHaveClass('text-white');

      const sellButton = screen.getByRole('radio', { name: /Sell/i });
      expect(sellButton).toHaveAttribute('aria-checked', 'false');
      expect(sellButton).not.toHaveClass('bg-red-500');
    });

    it('shows Sell as selected with red styling when direction is sell', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="sell" onDirectionChange={onChange} />
      );

      const sellButton = screen.getByRole('radio', { name: /Sell/i });
      expect(sellButton).toHaveAttribute('aria-checked', 'true');
      expect(sellButton).toHaveClass('bg-red-500');
      expect(sellButton).toHaveClass('text-white');

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      expect(buyButton).toHaveAttribute('aria-checked', 'false');
      expect(buyButton).not.toHaveClass('bg-green-500');
    });
  });

  // ============================================================================
  // Keyboard Shortcut Tests
  // ============================================================================

  describe('Keyboard Shortcuts', () => {
    it('selects Buy when B key is pressed', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="sell" onDirectionChange={onChange} />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      buyButton.focus();

      await user.keyboard('b');

      expect(onChange).toHaveBeenCalledWith('buy');
    });

    it('selects Sell when S key is pressed', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const sellButton = screen.getByRole('radio', { name: /Sell/i });
      sellButton.focus();

      await user.keyboard('s');

      expect(onChange).toHaveBeenCalledWith('sell');
    });

    it('toggles direction with ArrowLeft key', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      buyButton.focus();

      await user.keyboard('{ArrowLeft}');

      expect(onChange).toHaveBeenCalledWith('sell');
    });

    it('toggles direction with ArrowRight key', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="sell" onDirectionChange={onChange} />
      );

      const sellButton = screen.getByRole('radio', { name: /Sell/i });
      sellButton.focus();

      await user.keyboard('{ArrowRight}');

      expect(onChange).toHaveBeenCalledWith('buy');
    });
  });

  // ============================================================================
  // Disabled State Tests
  // ============================================================================

  describe('Disabled State', () => {
    it('applies disabled styling when disabled', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle
          direction="buy"
          onDirectionChange={onChange}
          disabled
        />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      const sellButton = screen.getByRole('radio', { name: /Sell/i });

      expect(buyButton).toBeDisabled();
      expect(sellButton).toBeDisabled();
      expect(buyButton).toHaveClass('cursor-not-allowed');
      expect(sellButton).toHaveClass('cursor-not-allowed');
    });

    it('does not call onDirectionChange when disabled', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle
          direction="buy"
          onDirectionChange={onChange}
          disabled
        />
      );

      const sellButton = screen.getByRole('radio', { name: /Sell/i });
      await user.click(sellButton);

      expect(onChange).not.toHaveBeenCalled();
    });

    it('does not respond to keyboard shortcuts when disabled', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle
          direction="buy"
          onDirectionChange={onChange}
          disabled
        />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      buyButton.focus();

      await user.keyboard('s');

      expect(onChange).not.toHaveBeenCalled();
    });

    it('shows reduced opacity when disabled', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle
          direction="buy"
          onDirectionChange={onChange}
          disabled
        />
      );

      const radiogroup = screen.getByRole('radiogroup');
      expect(radiogroup).toHaveClass('opacity-50');
    });
  });

  // ============================================================================
  // Accessibility Tests
  // ============================================================================

  describe('Accessibility', () => {
    it('has radiogroup role on container', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    });

    it('has aria-label on radiogroup', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      expect(screen.getByRole('radiogroup')).toHaveAttribute(
        'aria-label',
        'Select trade direction'
      );
    });

    it('has radio role on each button', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const radios = screen.getAllByRole('radio');
      expect(radios).toHaveLength(2);
    });

    it('has correct aria-checked attribute', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="sell" onDirectionChange={onChange} />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      const sellButton = screen.getByRole('radio', { name: /Sell/i });

      expect(buyButton).toHaveAttribute('aria-checked', 'false');
      expect(sellButton).toHaveAttribute('aria-checked', 'true');
    });

    it('includes keyboard shortcut in aria-label', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy \(B\)/i });
      const sellButton = screen.getByRole('radio', { name: /Sell \(S\)/i });

      expect(buyButton).toBeInTheDocument();
      expect(sellButton).toBeInTheDocument();
    });

    it('has correct tabIndex for roving tabindex', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      const sellButton = screen.getByRole('radio', { name: /Sell/i });

      // Selected item should have tabIndex 0
      expect(buyButton).toHaveAttribute('tabindex', '0');
      // Other items should have tabIndex -1
      expect(sellButton).toHaveAttribute('tabindex', '-1');
    });
  });

  // ============================================================================
  // Color Coding Tests
  // ============================================================================

  describe('Color Coding', () => {
    it('uses green colors for Buy button when selected', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const buyButton = screen.getByRole('radio', { name: /Buy/i });
      expect(buyButton).toHaveClass('bg-green-500');
      expect(buyButton).toHaveClass('text-white');
    });

    it('uses red colors for Sell button when selected', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="sell" onDirectionChange={onChange} />
      );

      const sellButton = screen.getByRole('radio', { name: /Sell/i });
      expect(sellButton).toHaveClass('bg-red-500');
      expect(sellButton).toHaveClass('text-white');
    });

    it('uses neutral colors for unselected buttons', () => {
      const onChange = vi.fn();
      render(
        <TradeDirectionToggle direction="buy" onDirectionChange={onChange} />
      );

      const sellButton = screen.getByRole('radio', { name: /Sell/i });
      expect(sellButton).toHaveClass('text-gray-600');
      expect(sellButton).toHaveClass('bg-transparent');
    });
  });
});
