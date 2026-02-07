/**
 * Outcome Selector Component Tests
 *
 * Tests for the OutcomeSelector component:
 * - Rendering outcomes with prices
 * - Selection behavior
 * - Keyboard navigation
 * - Disabled state
 * - Accessibility attributes
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OutcomeSelector, type Outcome } from '@/components/event/outcome-selector';

const mockOutcomes: Outcome[] = [
  {
    id: 'outcome-yes',
    tokenId: '123456789',
    outcomeName: 'Yes',
    currentPrice: 0.65,
  },
  {
    id: 'outcome-no',
    tokenId: '987654321',
    outcomeName: 'No',
    currentPrice: 0.35,
  },
];

const multiOutcomes: Outcome[] = [
  {
    id: 'outcome-1',
    tokenId: '111',
    outcomeName: 'Option A',
    currentPrice: 0.4,
  },
  {
    id: 'outcome-2',
    tokenId: '222',
    outcomeName: 'Option B',
    currentPrice: 0.3,
  },
  {
    id: 'outcome-3',
    tokenId: '333',
    outcomeName: 'Option C',
    currentPrice: 0.2,
  },
  {
    id: 'outcome-4',
    tokenId: '444',
    outcomeName: 'Option D',
    currentPrice: 0.1,
  },
];

describe('OutcomeSelector', () => {
  // ============================================================================
  // Rendering Tests
  // ============================================================================

  describe('Rendering', () => {
    it('renders all outcomes with names', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      expect(screen.getByText('Yes')).toBeInTheDocument();
      expect(screen.getByText('No')).toBeInTheDocument();
    });

    it('renders prices as cents', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      expect(screen.getByText('65¢')).toBeInTheDocument();
      expect(screen.getByText('35¢')).toBeInTheDocument();
    });

    it('renders "Select Outcome" label', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      expect(screen.getByText('Select Outcome')).toBeInTheDocument();
    });

    it('renders empty state when no outcomes provided', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={[]}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      expect(screen.getByText('No outcomes available')).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const onSelect = vi.fn();
      const { container } = render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
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
    it('calls onOutcomeSelect when an outcome is clicked', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      await user.click(yesButton);

      expect(onSelect).toHaveBeenCalledWith('outcome-yes');
    });

    it('highlights selected outcome with appropriate styling', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId="outcome-yes"
          onOutcomeSelect={onSelect}
        />
      );

      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      expect(yesButton).toHaveAttribute('aria-checked', 'true');
      expect(yesButton).toHaveClass('border-indigo-500');
      expect(yesButton).toHaveClass('bg-indigo-50');

      const noButton = screen.getByRole('radio', { name: /No/i });
      expect(noButton).toHaveAttribute('aria-checked', 'false');
      expect(noButton).not.toHaveClass('border-indigo-500');
    });

    it('shows radio indicator for selected outcome', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId="outcome-yes"
          onOutcomeSelect={onSelect}
        />
      );

      // The selected outcome should have a filled radio indicator
      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      const radioIndicator = yesButton.querySelector('.bg-indigo-500');
      expect(radioIndicator).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Keyboard Navigation Tests
  // ============================================================================

  describe('Keyboard Navigation', () => {
    it('navigates with ArrowDown key', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={multiOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const firstOption = screen.getByRole('radio', { name: /Option A/i });
      firstOption.focus();

      await user.keyboard('{ArrowDown}');

      const secondOption = screen.getByRole('radio', { name: /Option B/i });
      expect(document.activeElement).toBe(secondOption);
    });

    it('navigates with ArrowUp key', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={multiOutcomes}
          selectedOutcomeId="outcome-2"
          onOutcomeSelect={onSelect}
        />
      );

      const secondOption = screen.getByRole('radio', { name: /Option B/i });
      secondOption.focus();

      await user.keyboard('{ArrowUp}');

      const firstOption = screen.getByRole('radio', { name: /Option A/i });
      expect(document.activeElement).toBe(firstOption);
    });

    it('wraps navigation from last to first with ArrowDown', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={multiOutcomes}
          selectedOutcomeId="outcome-4"
          onOutcomeSelect={onSelect}
        />
      );

      const lastOption = screen.getByRole('radio', { name: /Option D/i });
      lastOption.focus();

      await user.keyboard('{ArrowDown}');

      const firstOption = screen.getByRole('radio', { name: /Option A/i });
      expect(document.activeElement).toBe(firstOption);
    });

    it('wraps navigation from first to last with ArrowUp', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={multiOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const firstOption = screen.getByRole('radio', { name: /Option A/i });
      firstOption.focus();

      await user.keyboard('{ArrowUp}');

      const lastOption = screen.getByRole('radio', { name: /Option D/i });
      expect(document.activeElement).toBe(lastOption);
    });

    it('selects outcome with Enter key', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      yesButton.focus();

      await user.keyboard('{Enter}');

      expect(onSelect).toHaveBeenCalledWith('outcome-yes');
    });

    it('selects outcome with Space key', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const noButton = screen.getByRole('radio', { name: /No/i });
      noButton.focus();

      await user.keyboard(' ');

      expect(onSelect).toHaveBeenCalledWith('outcome-no');
    });

    it('navigates to first option with Home key', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={multiOutcomes}
          selectedOutcomeId="outcome-3"
          onOutcomeSelect={onSelect}
        />
      );

      const thirdOption = screen.getByRole('radio', { name: /Option C/i });
      thirdOption.focus();

      await user.keyboard('{Home}');

      const firstOption = screen.getByRole('radio', { name: /Option A/i });
      expect(document.activeElement).toBe(firstOption);
    });

    it('navigates to last option with End key', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={multiOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const firstOption = screen.getByRole('radio', { name: /Option A/i });
      firstOption.focus();

      await user.keyboard('{End}');

      const lastOption = screen.getByRole('radio', { name: /Option D/i });
      expect(document.activeElement).toBe(lastOption);
    });
  });

  // ============================================================================
  // Disabled State Tests
  // ============================================================================

  describe('Disabled State', () => {
    it('applies disabled styling when disabled', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
          disabled
        />
      );

      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      expect(yesButton).toBeDisabled();
      expect(yesButton).toHaveClass('opacity-50');
      expect(yesButton).toHaveClass('cursor-not-allowed');
    });

    it('does not call onOutcomeSelect when disabled', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
          disabled
        />
      );

      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      await user.click(yesButton);

      expect(onSelect).not.toHaveBeenCalled();
    });
  });

  // ============================================================================
  // Accessibility Tests
  // ============================================================================

  describe('Accessibility', () => {
    it('has radiogroup role on container', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    });

    it('has aria-label on radiogroup', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      expect(screen.getByRole('radiogroup')).toHaveAttribute('aria-label', 'Select an outcome');
    });

    it('has radio role on each outcome', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const radios = screen.getAllByRole('radio');
      expect(radios).toHaveLength(2);
    });

    it('has correct aria-checked attribute', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId="outcome-no"
          onOutcomeSelect={onSelect}
        />
      );

      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      const noButton = screen.getByRole('radio', { name: /No/i });

      expect(yesButton).toHaveAttribute('aria-checked', 'false');
      expect(noButton).toHaveAttribute('aria-checked', 'true');
    });

    it('has correct tabIndex for roving tabindex', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId="outcome-yes"
          onOutcomeSelect={onSelect}
        />
      );

      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      const noButton = screen.getByRole('radio', { name: /No/i });

      // Selected item should have tabIndex 0
      expect(yesButton).toHaveAttribute('tabindex', '0');
      // Other items should have tabIndex -1
      expect(noButton).toHaveAttribute('tabindex', '-1');
    });

    it('first item has tabIndex 0 when none selected', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const yesButton = screen.getByRole('radio', { name: /Yes/i });
      const noButton = screen.getByRole('radio', { name: /No/i });

      // First item should have tabIndex 0 when none selected
      expect(yesButton).toHaveAttribute('tabindex', '0');
      expect(noButton).toHaveAttribute('tabindex', '-1');
    });
  });

  // ============================================================================
  // Price Display Tests
  // ============================================================================

  describe('Price Display', () => {
    it('displays prices with correct color coding', () => {
      const onSelect = vi.fn();
      render(
        <OutcomeSelector
          outcomes={mockOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      // 65% should have emerald/green color (medium-high probability)
      const highPrice = screen.getByText('65¢');
      expect(highPrice).toHaveClass('text-emerald-700');
      expect(highPrice).toHaveClass('bg-emerald-50');

      // 35% should have yellow color (medium probability)
      const lowPrice = screen.getByText('35¢');
      expect(lowPrice).toHaveClass('text-yellow-700');
      expect(lowPrice).toHaveClass('bg-yellow-50');
    });

    it('displays very low prices with red color', () => {
      const onSelect = vi.fn();
      const lowPriceOutcomes: Outcome[] = [
        {
          id: 'outcome-1',
          tokenId: '123',
          outcomeName: 'Unlikely',
          currentPrice: 0.05,
        },
      ];

      render(
        <OutcomeSelector
          outcomes={lowPriceOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const price = screen.getByText('5¢');
      expect(price).toHaveClass('text-red-700');
      expect(price).toHaveClass('bg-red-50');
    });

    it('displays high prices with green color', () => {
      const onSelect = vi.fn();
      const highPriceOutcomes: Outcome[] = [
        {
          id: 'outcome-1',
          tokenId: '123',
          outcomeName: 'Very Likely',
          currentPrice: 0.85,
        },
      ];

      render(
        <OutcomeSelector
          outcomes={highPriceOutcomes}
          selectedOutcomeId={null}
          onOutcomeSelect={onSelect}
        />
      );

      const price = screen.getByText('85¢');
      expect(price).toHaveClass('text-green-700');
      expect(price).toHaveClass('bg-green-50');
    });
  });
});
