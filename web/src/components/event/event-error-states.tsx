/**
 * Event Error State Components
 *
 * Sprint 01 - Event Page Foundation
 * PRD: error_handling
 *
 * Features:
 * - EventNotFound: Dedicated 404 state for missing events
 * - EventError: Generic error state with retry functionality
 * - Development mode console logging
 */

'use client';

import Link from 'next/link';
import { ArrowLeft, RefreshCw, Search, AlertCircle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

interface EventNotFoundProps {
  slug?: string;
}

/**
 * Dedicated 404 component for when an event is not found.
 * Provides helpful context and navigation options.
 */
export function EventNotFound({ slug }: EventNotFoundProps) {
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4">
      <Card className="max-w-lg w-full">
        <CardContent className="pt-8 pb-8">
          <div className="text-center space-y-6">
            {/* Icon */}
            <div className="mx-auto w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center">
              <Search className="h-8 w-8 text-gray-400" />
            </div>

            {/* Title */}
            <div className="space-y-2">
              <h1 className="text-2xl font-semibold text-gray-900">
                Event Not Found
              </h1>
              <p className="text-gray-600">
                The event you&apos;re looking for doesn&apos;t exist or may have been removed.
              </p>
              {slug && (
                <p className="text-sm text-gray-500">
                  Searched for: <code className="bg-gray-100 px-1.5 py-0.5 rounded">{slug}</code>
                </p>
              )}
            </div>

            {/* Suggestions */}
            <div className="text-sm text-gray-600 bg-gray-50 rounded-lg p-4">
              <p className="font-medium mb-2">This might have happened because:</p>
              <ul className="list-disc list-inside space-y-1 text-left">
                <li>The event has been resolved and removed</li>
                <li>The URL was typed incorrectly</li>
                <li>The event was moved or renamed</li>
              </ul>
            </div>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link
                href="/markets"
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-medium"
              >
                <Search className="h-4 w-4" />
                Browse Markets
              </Link>
              <Link
                href="/markets"
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-300 text-gray-700 bg-white rounded-lg hover:bg-gray-50 transition-colors font-medium"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to Markets
              </Link>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface EventErrorProps {
  title?: string;
  message: string;
  statusCode?: number;
  onRetry?: () => void;
  isRetrying?: boolean;
}

/**
 * Generic error component for API failures and other errors.
 * Displays user-friendly message with optional retry functionality.
 */
export function EventError({
  title,
  message,
  statusCode,
  onRetry,
  isRetrying = false,
}: EventErrorProps) {
  // Log error to console in development
  if (process.env.NODE_ENV === 'development') {
    console.error('[EventError]', { title, message, statusCode });
  }

  // Determine appropriate title based on status code
  const displayTitle = title || getErrorTitle(statusCode);
  const displayMessage = getUserFriendlyMessage(message, statusCode);

  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4">
      <Card className="max-w-lg w-full">
        <CardContent className="pt-8 pb-8">
          <div className="text-center space-y-6">
            {/* Icon */}
            <div className={`mx-auto w-16 h-16 rounded-full flex items-center justify-center ${
              statusCode === 429 ? 'bg-orange-100' :
              statusCode && statusCode >= 500 ? 'bg-red-100' :
              'bg-yellow-100'
            }`}>
              <AlertCircle className={`h-8 w-8 ${
                statusCode === 429 ? 'text-orange-500' :
                statusCode && statusCode >= 500 ? 'text-red-500' :
                'text-yellow-500'
              }`} />
            </div>

            {/* Title and Message */}
            <div className="space-y-2">
              <h1 className="text-2xl font-semibold text-gray-900">
                {displayTitle}
              </h1>
              <p className="text-gray-600">
                {displayMessage}
              </p>
              {statusCode && process.env.NODE_ENV === 'development' && (
                <p className="text-xs text-gray-400">
                  Status code: {statusCode}
                </p>
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              {onRetry && (
                <button
                  onClick={onRetry}
                  disabled={isRetrying}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <RefreshCw className={`h-4 w-4 ${isRetrying ? 'animate-spin' : ''}`} />
                  {isRetrying ? 'Retrying...' : 'Try Again'}
                </button>
              )}
              <Link
                href="/markets"
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-300 text-gray-700 bg-white rounded-lg hover:bg-gray-50 transition-colors font-medium"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to Markets
              </Link>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Get appropriate error title based on HTTP status code
 */
function getErrorTitle(statusCode?: number): string {
  if (!statusCode) return 'Error Loading Event';

  switch (statusCode) {
    case 400:
      return 'Invalid Request';
    case 401:
      return 'Authentication Required';
    case 403:
      return 'Access Denied';
    case 404:
      return 'Event Not Found';
    case 429:
      return 'Too Many Requests';
    case 500:
    case 502:
    case 503:
    case 504:
      return 'Server Error';
    default:
      return 'Error Loading Event';
  }
}

/**
 * Convert technical error messages to user-friendly text
 */
function getUserFriendlyMessage(message: string, statusCode?: number): string {
  // Handle specific status codes with user-friendly messages
  if (statusCode === 429) {
    return 'You\'ve made too many requests. Please wait a moment before trying again.';
  }

  if (statusCode && statusCode >= 500) {
    return 'Our servers are experiencing issues. Please try again in a few moments.';
  }

  if (statusCode === 401) {
    return 'You need to be logged in to view this event.';
  }

  if (statusCode === 403) {
    return 'You don\'t have permission to view this event.';
  }

  // Clean up technical error messages
  const lowercaseMessage = message.toLowerCase();

  if (lowercaseMessage.includes('network') || lowercaseMessage.includes('fetch')) {
    return 'Unable to connect to the server. Please check your internet connection and try again.';
  }

  if (lowercaseMessage.includes('timeout')) {
    return 'The request took too long. Please try again.';
  }

  // Return original message if it seems user-friendly enough
  if (message.length > 10 && !message.includes('Error:') && !message.includes('Exception')) {
    return message;
  }

  // Default fallback
  return 'Something went wrong while loading this event. Please try again.';
}
