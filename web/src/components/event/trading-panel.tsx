/**
 * Trading Panel Component
 *
 * Sprint 03 - Trading Panel UI
 * PRD: trading_panel_layout
 *
 * Features:
 * - Sticky positioning on desktop (below header)
 * - Card styling with border, shadow, and padding
 * - Collapsed/expanded state for mobile
 * - Expand button for mobile collapsed view
 * - Ensures panel doesn't overlap with footer on scroll
 */

'use client';

import { useState, useCallback, useEffect } from 'react';
import { ChevronUp, ChevronDown, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export interface TradingPanelProps {
  /** The event slug for navigation/API calls */
  eventSlug: string;
  /** Optional initial expanded state for mobile (default: false) */
  defaultExpanded?: boolean;
  /** Optional className for additional styling */
  className?: string;
  /** Children components (outcome selector, amount input, etc.) */
  children?: React.ReactNode;
}

/**
 * TradingPanel - Container component for trading interface
 *
 * On desktop: Displays as a sticky card in the sidebar
 * On mobile: Displays as a collapsible card that can be expanded/collapsed
 */
export function TradingPanel({
  eventSlug,
  defaultExpanded = false,
  className,
  children,
}: TradingPanelProps) {
  // Mobile expanded/collapsed state
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  // Track if we're on mobile for conditional rendering
  const [isMobile, setIsMobile] = useState(false);

  // Detect mobile viewport
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 1024); // lg breakpoint
    };

    // Initial check
    checkMobile();

    // Listen for resize
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Toggle expanded state
  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  // Handle keyboard navigation for the expand button
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleExpanded();
      }
    },
    [toggleExpanded]
  );

  return (
    <div
      className={cn(
        // Base styles
        'trading-panel',
        // Desktop: sticky positioning below header
        // The lg:top-24 accounts for the header height (approx 96px)
        // lg:max-h-[calc(100vh-8rem)] ensures panel doesn't extend past viewport
        // overflow-auto on desktop if content is too tall
        'lg:sticky lg:top-24 lg:max-h-[calc(100vh-8rem)] lg:overflow-auto',
        className
      )}
    >
      <Card className="overflow-hidden">
        {/* Header - always visible, clickable on mobile */}
        <CardHeader
          className={cn(
            'pb-3 flex flex-row items-center justify-between',
            // Mobile: make header clickable to expand/collapse
            isMobile && 'cursor-pointer hover:bg-gray-50 transition-colors'
          )}
          onClick={isMobile ? toggleExpanded : undefined}
          onKeyDown={isMobile ? handleKeyDown : undefined}
          role={isMobile ? 'button' : undefined}
          tabIndex={isMobile ? 0 : undefined}
          aria-expanded={isMobile ? isExpanded : undefined}
          aria-controls={isMobile ? 'trading-panel-content' : undefined}
        >
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-indigo-600" />
            Trade
          </CardTitle>

          {/* Mobile expand/collapse indicator */}
          {isMobile && (
            <button
              type="button"
              className="lg:hidden p-1.5 rounded-md hover:bg-gray-100 transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                toggleExpanded();
              }}
              aria-label={isExpanded ? 'Collapse trading panel' : 'Expand trading panel'}
            >
              {isExpanded ? (
                <ChevronUp className="h-5 w-5 text-gray-500" />
              ) : (
                <ChevronDown className="h-5 w-5 text-gray-500" />
              )}
            </button>
          )}
        </CardHeader>

        {/* Content - collapsible on mobile, always visible on desktop */}
        <div
          id="trading-panel-content"
          className={cn(
            'transition-all duration-300 ease-in-out',
            // Mobile collapsed state
            isMobile && !isExpanded && 'max-h-0 overflow-hidden opacity-0',
            // Mobile expanded or desktop state
            (isExpanded || !isMobile) && 'max-h-[2000px] opacity-100'
          )}
        >
          <CardContent className="space-y-4">
            {/* Mobile collapsed preview - shown when collapsed */}
            {isMobile && !isExpanded && (
              <div className="text-sm text-gray-500 text-center py-2">
                Tap to expand trading panel
              </div>
            )}

            {/* Trading panel children (outcome selector, amount input, etc.) */}
            {(!isMobile || isExpanded) && (
              <>
                {children || (
                  <TradingPanelPlaceholder eventSlug={eventSlug} />
                )}
              </>
            )}
          </CardContent>
        </div>

        {/* Mobile collapsed summary bar */}
        {isMobile && !isExpanded && (
          <div className="px-6 pb-4">
            <button
              type="button"
              onClick={toggleExpanded}
              className="w-full py-2.5 px-4 rounded-lg bg-indigo-50 text-indigo-700 text-sm font-medium hover:bg-indigo-100 transition-colors flex items-center justify-center gap-2"
            >
              <TrendingUp className="h-4 w-4" />
              Open Trading Panel
              <ChevronUp className="h-4 w-4" />
            </button>
          </div>
        )}
      </Card>
    </div>
  );
}

/**
 * Placeholder content for the trading panel
 * Will be replaced with actual trading components in subsequent sprints
 */
function TradingPanelPlaceholder({ eventSlug }: { eventSlug: string }) {
  return (
    <div className="space-y-4">
      {/* Placeholder for outcome selector */}
      <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-4 text-center">
        <p className="text-sm text-gray-500">Outcome Selector</p>
        <p className="text-xs text-gray-400 mt-1">Select an outcome to trade</p>
      </div>

      {/* Placeholder for trade direction */}
      <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-4 text-center">
        <p className="text-sm text-gray-500">Buy / Sell Toggle</p>
        <p className="text-xs text-gray-400 mt-1">Choose your trade direction</p>
      </div>

      {/* Placeholder for amount input */}
      <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-4 text-center">
        <p className="text-sm text-gray-500">Amount Input</p>
        <p className="text-xs text-gray-400 mt-1">Enter trade amount</p>
      </div>

      {/* Placeholder for trade summary */}
      <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-4 text-center">
        <p className="text-sm text-gray-500">Trade Summary</p>
        <p className="text-xs text-gray-400 mt-1">Review your order details</p>
      </div>

      {/* Placeholder submit button */}
      <button
        type="button"
        disabled
        className="w-full py-2.5 px-4 rounded-lg bg-gray-200 text-gray-500 text-sm font-medium cursor-not-allowed"
      >
        Trading Coming Soon
      </button>

      {/* Link to Polymarket */}
      <a
        href={`https://polymarket.com/event/${eventSlug}`}
        target="_blank"
        rel="noopener noreferrer"
        className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium border border-indigo-600 text-indigo-600 hover:bg-indigo-50 transition-colors"
      >
        Trade on Polymarket
        <svg
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
          />
        </svg>
      </a>
    </div>
  );
}

export default TradingPanel;
