/**
 * Event Detail Page Error Boundary
 *
 * Sprint 01 - Event Page Foundation
 * PRD: error_handling
 *
 * Next.js automatically uses this file to catch errors in the route segment.
 * Provides a fallback UI and recovery options.
 */

'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeft, RefreshCw, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function EventErrorBoundary({ error, reset }: ErrorProps) {
  // Log error to console in development mode
  useEffect(() => {
    if (process.env.NODE_ENV === 'development') {
      console.error('[EventErrorBoundary]', {
        message: error.message,
        digest: error.digest,
        stack: error.stack,
      });
    }
  }, [error]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4">
      <Card className="max-w-lg w-full">
        <CardContent className="pt-8 pb-8">
          <div className="text-center space-y-6">
            {/* Icon */}
            <div className="mx-auto w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
              <AlertTriangle className="h-8 w-8 text-red-500" />
            </div>

            {/* Title and Message */}
            <div className="space-y-2">
              <h1 className="text-2xl font-semibold text-gray-900">
                Something Went Wrong
              </h1>
              <p className="text-gray-600">
                An unexpected error occurred while loading this event.
                Our team has been notified and is working on a fix.
              </p>
              {process.env.NODE_ENV === 'development' && (
                <div className="mt-4 text-left bg-gray-50 rounded-lg p-4 overflow-auto">
                  <p className="text-xs text-gray-500 font-mono">
                    {error.message}
                  </p>
                  {error.digest && (
                    <p className="text-xs text-gray-400 mt-1">
                      Error ID: {error.digest}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button
                onClick={reset}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-medium"
              >
                <RefreshCw className="h-4 w-4" />
                Try Again
              </button>
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
