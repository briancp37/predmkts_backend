/**
 * Comments Tab Component
 *
 * Sprint 05 - Activity and Social
 * PRD: comments_placeholder
 *
 * Features:
 * - Display 'Comments coming soon' message with icon
 * - Show fake comment input (disabled) to show intent
 * - Add call-to-action to join community/Discord
 * - Style consistently with other tabs
 */

'use client';

import { MessageCircle, Send, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';

// =============================================================================
// Types
// =============================================================================

export interface CommentsTabProps {
  /** Optional Discord or community URL */
  communityUrl?: string;
  /** Optional className for the container */
  className?: string;
}

// =============================================================================
// Fake Comment Input (Disabled)
// =============================================================================

function FakeCommentInput() {
  return (
    <div className="relative">
      <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200 opacity-60">
        {/* Avatar placeholder */}
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
          <span className="text-xs text-gray-400">?</span>
        </div>

        {/* Input field (disabled) */}
        <input
          type="text"
          placeholder="Add a comment..."
          disabled
          className="flex-1 bg-transparent text-sm text-gray-400 placeholder-gray-400 cursor-not-allowed outline-none"
          aria-label="Comment input (coming soon)"
        />

        {/* Send button (disabled) */}
        <button
          type="button"
          disabled
          className="p-2 rounded-full bg-gray-200 text-gray-400 cursor-not-allowed"
          aria-label="Send comment (coming soon)"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>

      {/* Overlay indicator */}
      <div className="absolute inset-0 flex items-center justify-center bg-white/50 rounded-lg">
        <span className="text-xs font-medium text-gray-500 bg-white px-2 py-1 rounded shadow-sm">
          Coming Soon
        </span>
      </div>
    </div>
  );
}

// =============================================================================
// Community CTA
// =============================================================================

interface CommunityCTAProps {
  url?: string;
}

function CommunityCTA({ url }: CommunityCTAProps) {
  const discordUrl = url || 'https://discord.gg/polymarket';

  return (
    <div className="mt-6 p-4 bg-indigo-50 rounded-lg border border-indigo-100">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center">
          <MessageCircle className="h-5 w-5 text-indigo-600" />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-gray-900">
            Join the conversation
          </h4>
          <p className="mt-1 text-sm text-gray-600">
            While we build our comments feature, join our community to discuss markets and share insights.
          </p>
          <a
            href={discordUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 transition-colors"
          >
            Join Community
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Comments Tab Component
// =============================================================================

/**
 * CommentsTab - Placeholder comments section with coming soon message
 */
export function CommentsTab({ communityUrl, className }: CommentsTabProps) {
  return (
    <div className={cn('space-y-6', className)}>
      {/* Coming Soon Header */}
      <div className="text-center py-6">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 mb-4">
          <MessageCircle className="h-8 w-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-semibold text-gray-900">
          Comments Coming Soon
        </h3>
        <p className="mt-2 text-sm text-gray-500 max-w-md mx-auto">
          We're building a comments feature so you can discuss markets, share analysis, and connect with other traders.
        </p>
      </div>

      {/* Fake Comment Input */}
      <FakeCommentInput />

      {/* Community CTA */}
      <CommunityCTA url={communityUrl} />
    </div>
  );
}

export default CommentsTab;
