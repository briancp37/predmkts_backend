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
import { ChevronDown, ChevronUp, FileText, Scale, ExternalLink } from 'lucide-react';
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
