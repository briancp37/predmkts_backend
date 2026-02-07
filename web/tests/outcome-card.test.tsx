/**
 * Outcome Card Component Tests
 *
 * Tests for outcome card components:
 * - OutcomeCard component
 * - OutcomeCardList component
 * - Selection state handling
 * - Click and keyboard interactions
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  OutcomeCard,
  OutcomeCardList,
  type OutcomeCardData,
} from '@/components/event/outcome-card';

// ============================================================================
// Test Data
// ============================================================================

const mockOutcome: OutcomeCardData = {
  id: 'outcome-yes-123',
  tokenId: 'token123',
  outcomeName: 'Yes',
  currentPrice: 0.65,
  priceChange24h: 0.05,
  volume: 125000,
};

const mockOutcomeNegativeChange: OutcomeCardData = {
  id: 'outcome-no-456',
  tokenId: 'token456',
  outcomeName: 'No',
  currentPrice: 0.35,
  priceChange24h: -0.05,
  volume: 75000,
};

const mockOutcomeNoChange: OutcomeCardData = {
  id: 'outcome-maybe-789',
  tokenId: 'token789',
  outcomeName: 'Maybe',
  currentPrice: 0.2,
  priceChange24h: 0,
  volume: 50000,
};

const mockOutcomes: OutcomeCardData[] = [
  mockOutcome,
  mockOutcomeNegativeChange,
  mockOutcomeNoChange,
];

// ============================================================================
// OutcomeCard Tests
// ============================================================================

describe('OutcomeCard', () => {
  describe('rendering', () => {
    it('renders outcome name', () => {
      render(<OutcomeCard outcome={mockOutcome} />);
      expect(screen.getByText('Yes')).toBeInTheDocument();
    });

    it('renders probability as percentage', () => {
      render(<OutcomeCard outcome={mockOutcome} />);
      expect(screen.getByText('65%')).toBeInTheDocument();
    });

    it('renders probability as cents', () => {
      render(<OutcomeCard outcome={mockOutcome} />);
      expect(screen.getByText('65¢')).toBeInTheDocument();
    });

    it('renders positive 24h change with up arrow', () => {
      render(<OutcomeCard outcome={mockOutcome} />);
      expect(screen.getByText('↑')).toBeInTheDocument();
      expect(screen.getByText('5.0%')).toBeInTheDocument();
    });

    it('renders negative 24h change with down arrow', () => {
      render(<OutcomeCard outcome={mockOutcomeNegativeChange} />);
      expect(screen.getByText('↓')).toBeInTheDocument();
      expect(screen.getByText('5.0%')).toBeInTheDocument();
    });

    it('does not render change indicator when change is 0', () => {
      render(<OutcomeCard outcome={mockOutcomeNoChange} />);
      expect(screen.queryByText('↑')).not.toBeInTheDocument();
      expect(screen.queryByText('↓')).not.toBeInTheDocument();
    });

    it('does not render change indicator when priceChange24h is undefined', () => {
      const outcomeNoChange = { ...mockOutcome, priceChange24h: undefined };
      render(<OutcomeCard outcome={outcomeNoChange} />);
      expect(screen.queryByText('↑')).not.toBeInTheDocument();
    });
  });

  describe('color coding', () => {
    it('applies green colors for high probability (>=70%)', () => {
      const highProbOutcome = { ...mockOutcome, currentPrice: 0.75 };
      render(<OutcomeCard outcome={highProbOutcome} />);
      const priceElement = screen.getByText('75%');
      expect(priceElement).toHaveClass('bg-green-50');
      expect(priceElement).toHaveClass('text-green-700');
    });

    it('applies red colors for low probability (<15%)', () => {
      const lowProbOutcome = { ...mockOutcome, currentPrice: 0.1 };
      render(<OutcomeCard outcome={lowProbOutcome} />);
      const priceElement = screen.getByText('10%');
      expect(priceElement).toHaveClass('bg-red-50');
      expect(priceElement).toHaveClass('text-red-700');
    });
  });

  describe('selection state', () => {
    it('applies selected styles when isSelected is true', () => {
      const { container } = render(
        <OutcomeCard outcome={mockOutcome} isSelected />
      );
      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('border-indigo-500');
      expect(card).toHaveClass('bg-indigo-50');
    });

    it('applies unselected styles when isSelected is false', () => {
      const { container } = render(
        <OutcomeCard outcome={mockOutcome} isSelected={false} />
      );
      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('border-gray-200');
      expect(card).toHaveClass('bg-gray-50');
    });

    it('applies hover styles when clickable and unselected', () => {
      const { container } = render(
        <OutcomeCard outcome={mockOutcome} clickable isSelected={false} />
      );
      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('hover:border-gray-300');
      expect(card).toHaveClass('hover:bg-gray-100');
    });
  });

  describe('click interactions', () => {
    it('calls onSelect when clicked', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      render(<OutcomeCard outcome={mockOutcome} onSelect={onSelect} />);

      await user.click(screen.getByRole('button'));
      expect(onSelect).toHaveBeenCalledWith('outcome-yes-123');
    });

    it('does not call onSelect when clickable is false', async () => {
      const user = userEvent.setup();
      const onSelect = vi.fn();
      const { container } = render(
        <OutcomeCard outcome={mockOutcome} onSelect={onSelect} clickable={false} />
      );

      await user.click(container.firstChild as HTMLElement);
      expect(onSelect).not.toHaveBeenCalled();
    });

    it('does not render as button when clickable is false', () => {
      render(<OutcomeCard outcome={mockOutcome} clickable={false} />);
      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });
  });

  describe('keyboard interactions', () => {
    it('calls onSelect when Enter key is pressed', async () => {
      const onSelect = vi.fn();
      render(<OutcomeCard outcome={mockOutcome} onSelect={onSelect} />);

      const button = screen.getByRole('button');
      button.focus();
      fireEvent.keyDown(button, { key: 'Enter' });

      expect(onSelect).toHaveBeenCalledWith('outcome-yes-123');
    });

    it('calls onSelect when Space key is pressed', async () => {
      const onSelect = vi.fn();
      render(<OutcomeCard outcome={mockOutcome} onSelect={onSelect} />);

      const button = screen.getByRole('button');
      button.focus();
      fireEvent.keyDown(button, { key: ' ' });

      expect(onSelect).toHaveBeenCalledWith('outcome-yes-123');
    });

    it('does not call onSelect for other keys', async () => {
      const onSelect = vi.fn();
      render(<OutcomeCard outcome={mockOutcome} onSelect={onSelect} />);

      const button = screen.getByRole('button');
      button.focus();
      fireEvent.keyDown(button, { key: 'a' });

      expect(onSelect).not.toHaveBeenCalled();
    });
  });

  describe('accessibility', () => {
    it('has correct aria-pressed attribute when selected', () => {
      render(<OutcomeCard outcome={mockOutcome} isSelected />);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-pressed', 'true');
    });

    it('has correct aria-pressed attribute when not selected', () => {
      render(<OutcomeCard outcome={mockOutcome} isSelected={false} />);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-pressed', 'false');
    });

    it('has descriptive aria-label', () => {
      render(<OutcomeCard outcome={mockOutcome} />);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute(
        'aria-label',
        'Select Yes outcome at 65%'
      );
    });

    it('is focusable when clickable', () => {
      render(<OutcomeCard outcome={mockOutcome} clickable />);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('tabindex', '0');
    });
  });

  describe('size variants', () => {
    it('renders small size', () => {
      const { container } = render(
        <OutcomeCard outcome={mockOutcome} size="sm" />
      );
      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('p-2');
    });

    it('renders medium size (default)', () => {
      const { container } = render(<OutcomeCard outcome={mockOutcome} />);
      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('p-3');
    });
  });

  describe('custom className', () => {
    it('accepts custom className', () => {
      const { container } = render(
        <OutcomeCard outcome={mockOutcome} className="my-custom-class" />
      );
      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('my-custom-class');
    });
  });
});

// ============================================================================
// OutcomeCardList Tests
// ============================================================================

describe('OutcomeCardList', () => {
  describe('rendering', () => {
    it('renders all outcomes', () => {
      render(<OutcomeCardList outcomes={mockOutcomes} />);
      expect(screen.getByText('Yes')).toBeInTheDocument();
      expect(screen.getByText('No')).toBeInTheDocument();
      expect(screen.getByText('Maybe')).toBeInTheDocument();
    });

    it('renders empty state when no outcomes', () => {
      render(<OutcomeCardList outcomes={[]} />);
      expect(screen.getByText('No outcomes available')).toBeInTheDocument();
    });

    it('renders empty state when outcomes is undefined', () => {
      render(<OutcomeCardList outcomes={undefined as unknown as OutcomeCardData[]} />);
      expect(screen.getByText('No outcomes available')).toBeInTheDocument();
    });
  });

  describe('selection', () => {
    it('highlights selected outcome', () => {
      const { container } = render(
        <OutcomeCardList
          outcomes={mockOutcomes}
          selectedOutcomeId="outcome-yes-123"
        />
      );
      const selectedCard = container.querySelector('.border-indigo-500');
      expect(selectedCard).toBeInTheDocument();
    });

    it('calls onOutcomeSelect when outcome is clicked', async () => {
      const user = userEvent.setup();
      const onOutcomeSelect = vi.fn();
      render(
        <OutcomeCardList
          outcomes={mockOutcomes}
          onOutcomeSelect={onOutcomeSelect}
        />
      );

      await user.click(screen.getByText('Yes'));
      expect(onOutcomeSelect).toHaveBeenCalledWith('outcome-yes-123');
    });

    it('updates selection when different outcome is clicked', async () => {
      const user = userEvent.setup();
      const onOutcomeSelect = vi.fn();
      render(
        <OutcomeCardList
          outcomes={mockOutcomes}
          selectedOutcomeId="outcome-yes-123"
          onOutcomeSelect={onOutcomeSelect}
        />
      );

      await user.click(screen.getByText('No'));
      expect(onOutcomeSelect).toHaveBeenCalledWith('outcome-no-456');
    });
  });

  describe('layout', () => {
    it('renders vertical layout by default', () => {
      const { container } = render(<OutcomeCardList outcomes={mockOutcomes} />);
      const list = container.firstChild as HTMLElement;
      expect(list).toHaveClass('space-y-2');
    });

    it('renders horizontal layout when specified', () => {
      const { container } = render(
        <OutcomeCardList outcomes={mockOutcomes} layout="horizontal" />
      );
      const list = container.firstChild as HTMLElement;
      expect(list).toHaveClass('grid');
      expect(list).toHaveClass('grid-cols-2');
    });
  });

  describe('clickable prop', () => {
    it('passes clickable prop to all cards', () => {
      render(<OutcomeCardList outcomes={mockOutcomes} clickable={false} />);
      expect(screen.queryAllByRole('button')).toHaveLength(0);
    });

    it('makes cards clickable by default', () => {
      render(<OutcomeCardList outcomes={mockOutcomes} />);
      expect(screen.getAllByRole('button')).toHaveLength(3);
    });
  });

  describe('size prop', () => {
    it('passes size prop to all cards', () => {
      const { container } = render(
        <OutcomeCardList outcomes={mockOutcomes} size="sm" />
      );
      const cards = container.querySelectorAll('.p-2');
      expect(cards).toHaveLength(3);
    });
  });

  describe('custom className', () => {
    it('accepts custom className', () => {
      const { container } = render(
        <OutcomeCardList outcomes={mockOutcomes} className="my-custom-class" />
      );
      const list = container.firstChild as HTMLElement;
      expect(list).toHaveClass('my-custom-class');
    });
  });
});
