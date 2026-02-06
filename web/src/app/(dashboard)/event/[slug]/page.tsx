/**
 * Event Detail Page
 *
 * Sprint 01 - Event Page Foundation
 * PRD: frontend_routing
 *
 * Features:
 * - Dynamic route parameter extraction for slug
 * - Fetches event data with nested markets and outcomes
 * - Loading skeleton while fetching
 * - Error handling for 404 and API errors
 * - Basic event display with markets
 */

'use client';

import { use } from 'react';
import Link from 'next/link';
import { ArrowLeft, Tag, TrendingUp, TrendingDown } from 'lucide-react';
import { useEvent } from '@/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/loading-skeleton';

interface EventPageProps {
  params: Promise<{ slug: string }>;
}

/**
 * Format a price as a percentage (0-100)
 */
function formatPrice(price: number): string {
  return `${(price * 100).toFixed(1)}%`;
}

/**
 * Format price change with sign and color indicator
 */
function formatPriceChange(change: number): { text: string; isPositive: boolean } {
  const isPositive = change >= 0;
  const text = `${isPositive ? '+' : ''}${(change * 100).toFixed(1)}%`;
  return { text, isPositive };
}

/**
 * Format currency
 */
function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}K`;
  }
  return `$${value.toFixed(2)}`;
}

/**
 * Loading skeleton for event detail
 */
function EventDetailSkeleton() {
  return (
    <div className="space-y-6">
      {/* Back button skeleton */}
      <Skeleton className="h-10 w-24" />

      {/* Header skeleton */}
      <div className="space-y-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>

      {/* Markets skeleton */}
      <div className="grid gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-3/4" />
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/**
 * Error state component
 */
function EventError({ message, onRetry }: { message: string; onRetry: () => void }) {
  const isNotFound = message === 'Event not found';

  return (
    <div className="flex flex-col items-center justify-center py-12">
      <div className="text-center space-y-4">
        <h2 className="text-2xl font-semibold text-gray-900">
          {isNotFound ? 'Event Not Found' : 'Error Loading Event'}
        </h2>
        <p className="text-gray-600 max-w-md">
          {isNotFound
            ? "The event you're looking for doesn't exist or may have been removed."
            : message}
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/markets"
            className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md text-gray-700 bg-white hover:bg-gray-50 transition-colors"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Markets
          </Link>
          {!isNotFound && (
            <button
              onClick={onRetry}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors"
            >
              Try Again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function EventDetailPage({ params }: EventPageProps) {
  // Unwrap the params promise (Next.js 15 pattern)
  const { slug } = use(params);

  const {
    data: event,
    isLoading,
    error,
    refetch,
  } = useEvent(slug);

  // Loading state
  if (isLoading) {
    return <EventDetailSkeleton />;
  }

  // Error state
  if (error) {
    return (
      <EventError
        message={error instanceof Error ? error.message : 'Unknown error'}
        onRetry={() => refetch()}
      />
    );
  }

  // No data (shouldn't happen if no error, but handle gracefully)
  if (!event) {
    return (
      <EventError
        message="Event not found"
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Back navigation */}
      <Link
        href="/markets"
        className="inline-flex items-center text-gray-600 hover:text-gray-900 transition-colors"
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Markets
      </Link>

      {/* Event header */}
      <div className="space-y-2">
        {event.category && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Tag className="h-4 w-4" />
            <span>{event.category}</span>
          </div>
        )}
        <h1 className="text-2xl font-bold text-gray-900 md:text-3xl">
          {event.title}
        </h1>
        {event.description && (
          <p className="text-gray-600 max-w-3xl">
            {event.description}
          </p>
        )}
        <div className="flex items-center gap-4 text-sm text-gray-500">
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
            event.status === 'active'
              ? 'bg-green-100 text-green-800'
              : 'bg-gray-100 text-gray-800'
          }`}>
            {event.status}
          </span>
        </div>
      </div>

      {/* Markets */}
      {event.markets && event.markets.length > 0 ? (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Markets ({event.markets.length})
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {event.markets.map((market) => (
              <Card key={market.id} className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base font-medium leading-tight">
                    {market.question}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {/* Outcomes */}
                  {market.outcomes && market.outcomes.length > 0 && (
                    <div className="space-y-2">
                      {market.outcomes.map((outcome) => {
                        const priceChange = formatPriceChange(outcome.priceChange24h);
                        return (
                          <div
                            key={outcome.id}
                            className="flex items-center justify-between p-2 bg-gray-50 rounded"
                          >
                            <span className="font-medium text-sm">
                              {outcome.outcomeName}
                            </span>
                            <div className="flex items-center gap-3">
                              <span className="font-semibold">
                                {formatPrice(outcome.currentPrice)}
                              </span>
                              <span className={`flex items-center text-xs ${
                                priceChange.isPositive ? 'text-green-600' : 'text-red-600'
                              }`}>
                                {priceChange.isPositive ? (
                                  <TrendingUp className="h-3 w-3 mr-0.5" />
                                ) : (
                                  <TrendingDown className="h-3 w-3 mr-0.5" />
                                )}
                                {priceChange.text}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Market stats */}
                  <div className="flex items-center justify-between text-xs text-gray-500 pt-2 border-t">
                    <span>Volume: {formatCurrency(market.totalVolume)}</span>
                    <span>24h: {formatCurrency(market.volume24h ?? 0)}</span>
                    <span>Liquidity: {formatCurrency(market.liquidity)}</span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ) : (
        <Card>
          <CardContent className="py-8 text-center text-gray-500">
            No markets found for this event.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
