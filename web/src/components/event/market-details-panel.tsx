/**
 * Market Details Panel Component
 *
 * Sprint 02 - Market Display Components
 * PRD: market_details_panel
 *
 * Features:
 * - Display total volume with proper currency formatting
 * - Show end date with full date and time
 * - Show created date with relative time
 * - Display resolver address (truncated with copy button)
 * - Show market ID (truncated with copy button)
 * - Expandable section for additional metadata
 */

'use client';

import { memo, useState, useCallback } from 'react';
import { ChevronDown, ChevronUp, Copy, Check, Calendar, Clock, Hash, DollarSign, Droplets, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format a currency value with proper abbreviations
 * @param value - The value in USD
 * @returns Formatted string like "$66,109" or "$1.2M"
 */
export function formatCurrency(value: number): string {
  if (value >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
  }
  return `$${value.toFixed(2)}`;
}

/**
 * Format a date as full date and time
 * @param dateString - ISO 8601 date string
 * @returns Formatted string like "Jun 30, 2026, 11:59 PM"
 */
export function formatFullDateTime(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Format a date as relative time
 * @param dateString - ISO 8601 date string
 * @returns Formatted string like "2 weeks ago" or "3 months ago"
 */
export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);
  const diffYears = Math.floor(diffDays / 365);

  if (diffYears > 0) {
    return diffYears === 1 ? '1 year ago' : `${diffYears} years ago`;
  }
  if (diffMonths > 0) {
    return diffMonths === 1 ? '1 month ago' : `${diffMonths} months ago`;
  }
  if (diffWeeks > 0) {
    return diffWeeks === 1 ? '1 week ago' : `${diffWeeks} weeks ago`;
  }
  if (diffDays > 0) {
    return diffDays === 1 ? 'yesterday' : `${diffDays} days ago`;
  }
  if (diffHours > 0) {
    return diffHours === 1 ? '1 hour ago' : `${diffHours} hours ago`;
  }
  if (diffMinutes > 0) {
    return diffMinutes === 1 ? '1 minute ago' : `${diffMinutes} minutes ago`;
  }
  return 'just now';
}

/**
 * Truncate an address or ID for display
 * @param value - The full address or ID
 * @param startChars - Characters to show at start (default 6)
 * @param endChars - Characters to show at end (default 4)
 * @returns Truncated string like "0x1234...abcd"
 */
export function truncateAddress(value: string, startChars = 6, endChars = 4): string {
  if (value.length <= startChars + endChars + 3) {
    return value;
  }
  return `${value.slice(0, startChars)}...${value.slice(-endChars)}`;
}

// ============================================================================
// CopyButton Component
// ============================================================================

interface CopyButtonProps {
  value: string;
  label?: string;
  className?: string;
}

/**
 * Copy to clipboard button with feedback
 */
const CopyButton = memo(function CopyButton({
  value,
  label = 'Copy to clipboard',
  className,
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }, [value]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        'p-1 rounded hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
        className
      )}
      aria-label={copied ? 'Copied!' : label}
      title={copied ? 'Copied!' : label}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-green-600" />
      ) : (
        <Copy className="h-3.5 w-3.5 text-gray-400" />
      )}
    </button>
  );
});

// ============================================================================
// DetailRow Component
// ============================================================================

interface DetailRowProps {
  icon: React.ReactNode;
  label: string;
  value: string | React.ReactNode;
  copyValue?: string;
  className?: string;
}

/**
 * Single row in the details panel
 */
const DetailRow = memo(function DetailRow({
  icon,
  label,
  value,
  copyValue,
  className,
}: DetailRowProps) {
  return (
    <div className={cn('flex items-start gap-3 py-2', className)}>
      <div className="flex-shrink-0 mt-0.5 text-gray-400">{icon}</div>
      <div className="flex-1 min-w-0">
        <dt className="text-xs text-gray-500 font-medium uppercase tracking-wider">
          {label}
        </dt>
        <dd className="mt-0.5 flex items-center gap-1.5">
          <span className="text-sm text-gray-900 font-mono truncate">
            {value}
          </span>
          {copyValue && <CopyButton value={copyValue} label={`Copy ${label}`} />}
        </dd>
      </div>
    </div>
  );
});

// ============================================================================
// MarketDetailsPanel Component
// ============================================================================

export interface MarketDetailsPanelProps {
  /** Total trading volume in USD */
  volume?: number | null;
  /** Current liquidity in USD */
  liquidity?: number | null;
  /** Market resolution deadline (ISO 8601) */
  endDate?: string | null;
  /** Market creation timestamp (ISO 8601) */
  createdAt?: string | null;
  /** Resolver address (e.g., 0x...) */
  resolverAddress?: string | null;
  /** Market ID */
  marketId?: string | null;
  /** Polymarket condition ID */
  conditionId?: string | null;
  /** Market slug */
  slug?: string | null;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Market Details Panel - Displays market metadata in a sidebar panel
 *
 * Shows essential market information including volume, dates, and identifiers.
 * Includes an expandable section for additional metadata.
 *
 * @example
 * ```tsx
 * <MarketDetailsPanel
 *   volume={66109}
 *   liquidity={25000}
 *   endDate="2026-06-30T23:59:59Z"
 *   createdAt="2024-01-15T10:30:00Z"
 *   resolverAddress="0x1234567890abcdef1234567890abcdef12345678"
 *   marketId="market-12345"
 * />
 * ```
 */
export const MarketDetailsPanel = memo(function MarketDetailsPanel({
  volume,
  liquidity,
  endDate,
  createdAt,
  resolverAddress,
  marketId,
  conditionId,
  slug,
  className,
}: MarketDetailsPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  // Check if there's any additional metadata to show in the expandable section
  const hasAdditionalMetadata = conditionId || slug;

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Market Details</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="divide-y divide-gray-100">
          {/* Volume */}
          {volume !== null && volume !== undefined && (
            <DetailRow
              icon={<DollarSign className="h-4 w-4" />}
              label="Total Volume"
              value={formatCurrency(volume)}
            />
          )}

          {/* Liquidity */}
          {liquidity !== null && liquidity !== undefined && (
            <DetailRow
              icon={<Droplets className="h-4 w-4" />}
              label="Liquidity"
              value={formatCurrency(liquidity)}
            />
          )}

          {/* End Date */}
          {endDate && (
            <DetailRow
              icon={<Calendar className="h-4 w-4" />}
              label="Resolution Date"
              value={formatFullDateTime(endDate)}
            />
          )}

          {/* Created Date */}
          {createdAt && (
            <DetailRow
              icon={<Clock className="h-4 w-4" />}
              label="Created"
              value={
                <span title={formatFullDateTime(createdAt)}>
                  {formatRelativeTime(createdAt)}
                </span>
              }
            />
          )}

          {/* Resolver Address */}
          {resolverAddress && (
            <DetailRow
              icon={<User className="h-4 w-4" />}
              label="Resolver"
              value={truncateAddress(resolverAddress)}
              copyValue={resolverAddress}
            />
          )}

          {/* Market ID */}
          {marketId && (
            <DetailRow
              icon={<Hash className="h-4 w-4" />}
              label="Market ID"
              value={truncateAddress(marketId, 8, 6)}
              copyValue={marketId}
            />
          )}
        </dl>

        {/* Expandable Additional Metadata */}
        {hasAdditionalMetadata && (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <button
              type="button"
              onClick={toggleExpanded}
              className="flex items-center justify-between w-full text-sm text-gray-600 hover:text-gray-900 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 rounded px-1 py-0.5 -mx-1"
              aria-expanded={isExpanded}
            >
              <span className="font-medium">Additional Details</span>
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </button>

            {isExpanded && (
              <dl className="mt-2 divide-y divide-gray-100">
                {/* Condition ID */}
                {conditionId && (
                  <DetailRow
                    icon={<Hash className="h-4 w-4" />}
                    label="Condition ID"
                    value={truncateAddress(conditionId, 8, 6)}
                    copyValue={conditionId}
                  />
                )}

                {/* Slug */}
                {slug && (
                  <DetailRow
                    icon={<Hash className="h-4 w-4" />}
                    label="Slug"
                    value={
                      slug.length > 30
                        ? `${slug.slice(0, 27)}...`
                        : slug
                    }
                    copyValue={slug}
                  />
                )}
              </dl>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
});

export default MarketDetailsPanel;
