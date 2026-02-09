/**
 * Resolution Rules Component
 *
 * Sprint 02 - Market Display Components
 * PRD: resolution_rules
 *
 * Features:
 * - Display event description with proper formatting
 * - Collapsible section for long descriptions
 * - Show resolver type and source information
 * - Disabled 'Propose Resolution' button placeholder
 */

'use client';

import { memo, useState, useCallback, useMemo } from 'react';
import { ChevronDown, ChevronUp, FileText, Scale, ExternalLink, Calendar, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// ============================================================================
// Constants
// ============================================================================

const COLLAPSED_LINE_COUNT = 6;
const APPROXIMATE_CHARS_PER_LINE = 80;
const COLLAPSE_THRESHOLD = COLLAPSED_LINE_COUNT * APPROXIMATE_CHARS_PER_LINE;

// ============================================================================
// Types
// ============================================================================

export interface ResolutionRulesProps {
  /** Event/market description containing resolution criteria */
  description?: string | null;
  /** Type of resolver (e.g., "UMA Optimistic Oracle", "Polymarket") */
  resolverType?: string | null;
  /** Resolution source information (e.g., "Official government data") */
  resolutionSource?: string | null;
  /** Whether the market has been resolved */
  isResolved?: boolean;
  /** Resolution outcome (if resolved) */
  resolutionOutcome?: string | null;
  /** Market resolution deadline (ISO 8601) */
  endDate?: string | null;
  /** Additional CSS classes */
  className?: string;
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Parse description text and extract key resolution criteria
 * Looks for common patterns like "Resolution:", "Criteria:", bullet points, etc.
 */
function parseResolutionCriteria(description: string): {
  mainText: string;
  criteria: string[];
} {
  const criteria: string[] = [];
  const lines = description.split('\n');
  const mainTextLines: string[] = [];

  for (const line of lines) {
    const trimmedLine = line.trim();

    // Detect criteria section headers (skip these lines)
    if (/^(resolution|criteria|rules|conditions):/i.test(trimmedLine)) {
      continue;
    }

    // Detect bullet points or numbered items as criteria
    if (/^[-•*]\s+/.test(trimmedLine) || /^\d+[.)]\s+/.test(trimmedLine)) {
      const cleanedCriteria = trimmedLine.replace(/^[-•*\d.)\s]+/, '').trim();
      if (cleanedCriteria) {
        criteria.push(cleanedCriteria);
      }
      continue;
    }

    // Add to main text
    if (trimmedLine) {
      mainTextLines.push(trimmedLine);
    }
  }

  return {
    mainText: mainTextLines.join('\n\n'),
    criteria,
  };
}

/**
 * Check if description is long enough to warrant collapsing
 */
function shouldCollapse(text: string): boolean {
  return text.length > COLLAPSE_THRESHOLD;
}

/**
 * Format end date for display
 * Shows date with time and relative indicator (e.g., "in 3 days", "2 hours ago")
 */
function formatEndDate(dateString: string): { formatted: string; relative: string; isPast: boolean } {
  const date = new Date(dateString);
  const now = new Date();
  const isPast = date < now;

  // Format the date: "Jan 15, 2025 at 11:59 PM"
  const formatted = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }) + ' at ' + date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });

  // Calculate relative time
  const diffMs = Math.abs(date.getTime() - now.getTime());
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  let relative: string;
  if (diffMinutes < 60) {
    relative = diffMinutes === 1 ? '1 minute' : `${diffMinutes} minutes`;
  } else if (diffHours < 24) {
    relative = diffHours === 1 ? '1 hour' : `${diffHours} hours`;
  } else if (diffDays < 30) {
    relative = diffDays === 1 ? '1 day' : `${diffDays} days`;
  } else {
    const diffMonths = Math.floor(diffDays / 30);
    relative = diffMonths === 1 ? '1 month' : `${diffMonths} months`;
  }

  relative = isPast ? `${relative} ago` : `in ${relative}`;

  return { formatted, relative, isPast };
}

// ============================================================================
// EndDateDisplay Component
// ============================================================================

interface EndDateDisplayProps {
  endDate: string;
  isResolved?: boolean;
}

const EndDateDisplay = memo(function EndDateDisplay({
  endDate,
  isResolved = false,
}: EndDateDisplayProps) {
  const { formatted, relative, isPast } = useMemo(() => formatEndDate(endDate), [endDate]);

  // Determine styling based on status
  const isOverdue = isPast && !isResolved;
  const isUpcoming = !isPast && !isResolved;

  return (
    <div
      className={`mb-4 p-3 rounded-lg border flex items-start gap-3 ${
        isResolved
          ? 'bg-gray-50 border-gray-200'
          : isOverdue
            ? 'bg-amber-50 border-amber-200'
            : isUpcoming
              ? 'bg-indigo-50 border-indigo-200'
              : 'bg-gray-50 border-gray-200'
      }`}
    >
      <div
        className={`flex items-center justify-center h-9 w-9 rounded-full flex-shrink-0 ${
          isResolved
            ? 'bg-gray-100'
            : isOverdue
              ? 'bg-amber-100'
              : 'bg-indigo-100'
        }`}
      >
        {isPast ? (
          <Clock
            className={`h-4 w-4 ${
              isResolved ? 'text-gray-500' : 'text-amber-600'
            }`}
          />
        ) : (
          <Calendar
            className={`h-4 w-4 ${
              isResolved ? 'text-gray-500' : 'text-indigo-600'
            }`}
          />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span
            className={`text-sm font-semibold ${
              isResolved
                ? 'text-gray-700'
                : isOverdue
                  ? 'text-amber-800'
                  : 'text-indigo-800'
            }`}
          >
            {isResolved ? 'Ended' : isPast ? 'Resolution Overdue' : 'Resolution Deadline'}
          </span>
          <span
            className={`text-xs font-medium ${
              isResolved
                ? 'text-gray-500'
                : isOverdue
                  ? 'text-amber-600'
                  : 'text-indigo-600'
            }`}
          >
            ({relative})
          </span>
        </div>
        <p
          className={`text-sm mt-0.5 ${
            isResolved
              ? 'text-gray-600'
              : isOverdue
                ? 'text-amber-700'
                : 'text-indigo-700'
          }`}
        >
          {formatted}
        </p>
      </div>
    </div>
  );
});

// ============================================================================
// ResolutionCriteriaList Component
// ============================================================================

interface ResolutionCriteriaListProps {
  criteria: string[];
}

const ResolutionCriteriaList = memo(function ResolutionCriteriaList({
  criteria,
}: ResolutionCriteriaListProps) {
  if (criteria.length === 0) return null;

  return (
    <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-100">
      <h4 className="text-sm font-semibold text-blue-900 mb-2 flex items-center gap-1.5">
        <Scale className="h-4 w-4" />
        Key Resolution Criteria
      </h4>
      <ul className="space-y-1.5">
        {criteria.map((criterion, index) => (
          <li
            key={index}
            className="text-sm text-blue-800 flex items-start gap-2"
          >
            <span className="text-blue-400 mt-1 flex-shrink-0">•</span>
            <span>{criterion}</span>
          </li>
        ))}
      </ul>
    </div>
  );
});

// ============================================================================
// DescriptionText Component
// ============================================================================

interface DescriptionTextProps {
  text: string;
  isExpanded: boolean;
}

const DescriptionText = memo(function DescriptionText({
  text,
  isExpanded,
}: DescriptionTextProps) {
  const displayText = useMemo(() => {
    if (isExpanded || !shouldCollapse(text)) {
      return text;
    }
    // Truncate at the collapse threshold, trying to break at a word boundary
    const truncated = text.slice(0, COLLAPSE_THRESHOLD);
    const lastSpace = truncated.lastIndexOf(' ');
    return lastSpace > COLLAPSE_THRESHOLD * 0.8
      ? truncated.slice(0, lastSpace) + '...'
      : truncated + '...';
  }, [text, isExpanded]);

  // Split into paragraphs for proper rendering
  const paragraphs = displayText.split('\n\n').filter(Boolean);

  return (
    <div className="prose prose-sm max-w-none text-gray-700">
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="mb-3 last:mb-0 leading-relaxed">
          {paragraph}
        </p>
      ))}
    </div>
  );
});

// ============================================================================
// ResolverInfo Component
// ============================================================================

interface ResolverInfoProps {
  resolverType?: string | null;
  resolutionSource?: string | null;
}

const ResolverInfo = memo(function ResolverInfo({
  resolverType,
  resolutionSource,
}: ResolverInfoProps) {
  if (!resolverType && !resolutionSource) return null;

  return (
    <div className="mt-4 pt-4 border-t border-gray-100">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        Resolution Information
      </h4>
      <dl className="space-y-2">
        {resolverType && (
          <div className="flex items-start gap-2">
            <dt className="text-xs text-gray-500 min-w-20">Resolver:</dt>
            <dd className="text-sm text-gray-900 font-medium">{resolverType}</dd>
          </div>
        )}
        {resolutionSource && (
          <div className="flex items-start gap-2">
            <dt className="text-xs text-gray-500 min-w-20">Source:</dt>
            <dd className="text-sm text-gray-900">{resolutionSource}</dd>
          </div>
        )}
      </dl>
    </div>
  );
});

// ============================================================================
// ResolutionRules Component
// ============================================================================

/**
 * Resolution Rules - Displays market resolution criteria and rules
 *
 * Shows the event/market description with highlighted resolution criteria,
 * resolver information, and a placeholder for proposing resolutions.
 *
 * @example
 * ```tsx
 * <ResolutionRules
 *   description="This market will resolve to Yes if Bitcoin reaches $100,000..."
 *   resolverType="UMA Optimistic Oracle"
 *   resolutionSource="CoinGecko price data"
 * />
 * ```
 */
export const ResolutionRules = memo(function ResolutionRules({
  description,
  resolverType,
  resolutionSource,
  isResolved = false,
  resolutionOutcome,
  endDate,
  className,
}: ResolutionRulesProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  // Parse description to extract criteria
  const { mainText, criteria } = useMemo(() => {
    if (!description) {
      return { mainText: '', criteria: [] };
    }
    return parseResolutionCriteria(description);
  }, [description]);

  const hasDescription = Boolean(description?.trim());
  const isLongDescription = hasDescription && shouldCollapse(description || '');

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <FileText className="h-4 w-4 text-gray-500" />
          Resolution Rules
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Resolved Status Banner */}
        {isResolved && (
          <div className="mb-4 p-3 bg-green-50 rounded-lg border border-green-200">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-green-800">
                Resolved
              </span>
              {resolutionOutcome && (
                <span className="text-sm text-green-700">
                  — {resolutionOutcome}
                </span>
              )}
            </div>
          </div>
        )}

        {/* End Date / Resolution Deadline */}
        {endDate && (
          <EndDateDisplay endDate={endDate} isResolved={isResolved} />
        )}

        {/* Description */}
        {hasDescription ? (
          <>
            <DescriptionText text={mainText || description || ''} isExpanded={isExpanded} />

            {/* Show/Hide Button for Long Descriptions */}
            {isLongDescription && (
              <button
                type="button"
                onClick={toggleExpanded}
                className="mt-2 flex items-center gap-1 text-sm text-indigo-600 hover:text-indigo-800 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 rounded px-1 py-0.5 -mx-1"
                aria-expanded={isExpanded}
              >
                {isExpanded ? (
                  <>
                    Show less <ChevronUp className="h-4 w-4" />
                  </>
                ) : (
                  <>
                    Show more <ChevronDown className="h-4 w-4" />
                  </>
                )}
              </button>
            )}

            {/* Highlighted Criteria */}
            {criteria.length > 0 && <ResolutionCriteriaList criteria={criteria} />}
          </>
        ) : (
          <p className="text-sm text-gray-500 italic">
            No resolution rules available for this market.
          </p>
        )}

        {/* Resolver Information */}
        <ResolverInfo
          resolverType={resolverType}
          resolutionSource={resolutionSource}
        />

        {/* Propose Resolution Button (Disabled Placeholder) */}
        {!isResolved && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <button
              type="button"
              disabled
              className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-gray-400 bg-gray-100 rounded-lg cursor-not-allowed"
              title="Proposing resolutions is not yet available"
            >
              <ExternalLink className="h-4 w-4" />
              Propose Resolution
            </button>
            <p className="mt-1.5 text-xs text-gray-400 text-center">
              Resolution proposals coming soon
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
});

export default ResolutionRules;
