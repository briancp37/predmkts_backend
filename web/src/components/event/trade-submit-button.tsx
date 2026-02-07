/**
 * Trade Submit Button Component
 *
 * Sprint 03 - Trading Panel UI
 * PRD: dummy_trade_button
 *
 * Features:
 * - Primary action button (full width, prominent)
 * - Shows 'Buy [Outcome]' or 'Sell [Outcome]' text
 * - Loading state during 'submission'
 * - On click: shows toast notification 'Trading coming soon!'
 * - Confetti animation on success feedback
 * - Disabled when amount is invalid or no outcome selected
 */

'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TradeDirection } from './trade-direction-toggle';

export interface TradeSubmitButtonProps {
  /** Selected outcome name */
  outcomeName: string | null;
  /** Trade direction (buy/sell) */
  direction: TradeDirection;
  /** Trade amount in USD */
  amount: number | null;
  /** Whether the button should be disabled */
  disabled?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Toast notification component for displaying messages
 */
interface ToastProps {
  message: string;
  type: 'success' | 'info';
  onClose: () => void;
}

const Toast = memo(function Toast({ message, type, onClose }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div
      className={cn(
        'fixed bottom-4 left-1/2 -translate-x-1/2 z-50',
        'flex items-center gap-2 rounded-lg px-4 py-3 shadow-lg',
        'animate-in slide-in-from-bottom-4 fade-in duration-300',
        type === 'success' ? 'bg-green-600 text-white' : 'bg-indigo-600 text-white'
      )}
      role="alert"
      aria-live="polite"
    >
      <span className="text-sm font-medium">{message}</span>
      <button
        onClick={onClose}
        className="ml-2 rounded p-1 hover:bg-white/20 transition-colors"
        aria-label="Dismiss notification"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
});

/**
 * Confetti piece component
 */
interface ConfettiPieceProps {
  color: string;
  left: number;
  delay: number;
}

const ConfettiPiece = memo(function ConfettiPiece({ color, left, delay }: ConfettiPieceProps) {
  return (
    <div
      className="absolute w-2 h-2 rounded-sm animate-confetti"
      style={{
        backgroundColor: color,
        left: `${left}%`,
        animationDelay: `${delay}ms`,
        top: 0,
      }}
    />
  );
});

/**
 * Confetti animation component
 */
const Confetti = memo(function Confetti() {
  const colors = ['#22c55e', '#3b82f6', '#f59e0b', '#ec4899', '#8b5cf6', '#14b8a6'] as const;
  const pieces = Array.from({ length: 20 }, (_, i) => ({
    id: i,
    color: colors[i % colors.length] as string,
    left: Math.random() * 100,
    delay: Math.random() * 300,
  }));

  return (
    <div className="fixed inset-0 pointer-events-none z-50 overflow-hidden">
      {pieces.map((piece) => (
        <ConfettiPiece key={piece.id} color={piece.color} left={piece.left} delay={piece.delay} />
      ))}
    </div>
  );
});

/**
 * TradeSubmitButton - Primary action button for trade submission
 */
export const TradeSubmitButton = memo(function TradeSubmitButton({
  outcomeName,
  direction,
  amount,
  disabled = false,
  className,
}: TradeSubmitButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const [showConfetti, setShowConfetti] = useState(false);

  // Determine if button should be disabled
  const isValidAmount = amount !== null && amount >= 1;
  const hasOutcome = outcomeName !== null;
  const isDisabled = disabled || !isValidAmount || !hasOutcome || isLoading;

  // Generate button text based on direction and outcome
  const buttonText = hasOutcome
    ? `${direction === 'buy' ? 'Buy' : 'Sell'} ${outcomeName}`
    : direction === 'buy'
      ? 'Buy'
      : 'Sell';

  // Handle click with loading state and animations
  const handleClick = useCallback(async () => {
    if (isDisabled) return;

    setIsLoading(true);

    // Simulate a short "submission" delay
    await new Promise((resolve) => setTimeout(resolve, 800));

    setIsLoading(false);
    setShowToast(true);
    setShowConfetti(true);

    // Remove confetti after animation completes
    setTimeout(() => setShowConfetti(false), 2000);
  }, [isDisabled]);

  // Close toast handler
  const handleCloseToast = useCallback(() => {
    setShowToast(false);
  }, []);

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        disabled={isDisabled}
        className={cn(
          // Base styles
          'w-full py-3 px-4 rounded-lg text-sm font-semibold transition-all duration-200',
          'flex items-center justify-center gap-2',
          // Enabled state - color based on direction
          !isDisabled && direction === 'buy' && [
            'bg-green-600 text-white',
            'hover:bg-green-700',
            'active:bg-green-800 active:scale-[0.98]',
            'focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2',
          ],
          !isDisabled && direction === 'sell' && [
            'bg-red-600 text-white',
            'hover:bg-red-700',
            'active:bg-red-800 active:scale-[0.98]',
            'focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2',
          ],
          // Disabled state
          isDisabled && 'bg-gray-200 text-gray-500 cursor-not-allowed',
          // Loading state
          isLoading && 'cursor-wait',
          className
        )}
        aria-disabled={isDisabled}
        aria-busy={isLoading}
      >
        {isLoading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span>Processing...</span>
          </>
        ) : (
          <span>{buttonText}</span>
        )}
      </button>

      {/* Toast notification */}
      {showToast && (
        <Toast
          message="Trading coming soon!"
          type="info"
          onClose={handleCloseToast}
        />
      )}

      {/* Confetti animation */}
      {showConfetti && <Confetti />}

      {/* CSS for confetti animation */}
      <style jsx global>{`
        @keyframes confetti-fall {
          0% {
            transform: translateY(-10vh) rotate(0deg);
            opacity: 1;
          }
          100% {
            transform: translateY(100vh) rotate(720deg);
            opacity: 0;
          }
        }
        .animate-confetti {
          animation: confetti-fall 2s ease-out forwards;
        }
      `}</style>
    </>
  );
});

export default TradeSubmitButton;
