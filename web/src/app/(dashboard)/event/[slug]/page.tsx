/**
 * Event Detail Page
 *
 * Sprint 01 - Event Page Foundation
 * PRD: frontend_routing, page_layout
 *
 * Features:
 * - Dynamic route parameter extraction for slug
 * - Fetches event data with nested markets and outcomes
 * - Two-column layout: main content + sidebar
 * - Responsive: single column mobile, two columns desktop
 * - Sticky sidebar on desktop
 * - Breadcrumb navigation: Markets > Category > Event Title
 * - Loading skeleton while fetching
 * - Error handling for 404 and API errors
 */

'use client';

import { use, useEffect } from 'react';
import { Tag, TrendingUp, TrendingDown, Clock, BarChart2 } from 'lucide-react';
import { useEvent } from '@/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EventDetailPageSkeleton } from '@/components/loading-skeleton';
import { EventDetailLayout, SectionPlaceholder, EventNotFound, EventError, ActivityTabs, TradingPanel, type Outcome } from '@/components/event';

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
 * Event Header Component
 */
function EventHeader({
  title,
  description,
  category,
  status,
}: {
  title: string;
  description?: string | null;
  category?: string | null;
  status: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6 space-y-3">
        {/* Category Badge */}
        {category && (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700">
              <Tag className="h-3 w-3" />
              {category}
            </span>
          </div>
        )}

        {/* Title */}
        <h1 className="text-2xl font-bold text-gray-900 md:text-3xl">
          {title}
        </h1>

        {/* Description */}
        {description && (
          <p className="text-gray-600 leading-relaxed">
            {description}
          </p>
        )}

        {/* Status and Metadata */}
        <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-gray-100">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
              status === 'active'
                ? 'bg-green-100 text-green-800'
                : 'bg-gray-100 text-gray-800'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${
              status === 'active' ? 'bg-green-500' : 'bg-gray-500'
            }`} />
            {status === 'active' ? 'Active' : status}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Outcomes List Component
 */
function OutcomesList({
  markets,
}: {
  markets: Array<{
    id: string;
    question: string;
    totalVolume: number;
    liquidity: number;
    volume24h?: number;
    outcomes?: Array<{
      id: string;
      outcomeName: string;
      currentPrice: number;
      priceChange24h: number;
    }>;
  }>;
}) {
  if (!markets || markets.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-gray-500">
          No markets found for this event.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {markets.map((market) => (
        <Card key={market.id}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-medium leading-tight flex items-start justify-between gap-4">
              <span>{market.question}</span>
              <BarChart2 className="h-4 w-4 text-gray-400 flex-shrink-0 mt-0.5" />
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
                      className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                    >
                      <span className="font-medium text-gray-900">
                        {outcome.outcomeName}
                      </span>
                      <div className="flex items-center gap-4">
                        <span className="text-lg font-semibold text-gray-900">
                          {formatPrice(outcome.currentPrice)}
                        </span>
                        <span
                          className={`flex items-center gap-1 text-sm font-medium ${
                            priceChange.isPositive ? 'text-green-600' : 'text-red-600'
                          }`}
                        >
                          {priceChange.isPositive ? (
                            <TrendingUp className="h-4 w-4" />
                          ) : (
                            <TrendingDown className="h-4 w-4" />
                          )}
                          {priceChange.text}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Market Stats */}
            <div className="flex items-center justify-between text-sm text-gray-500 pt-3 border-t">
              <div className="flex items-center gap-4">
                <span>Volume: {formatCurrency(market.totalVolume)}</span>
                <span>24h: {formatCurrency(market.volume24h ?? 0)}</span>
              </div>
              <span>Liquidity: {formatCurrency(market.liquidity)}</span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/**
 * Trading Panel Sidebar Component
 * Uses the TradingPanel component for the trading interface
 */
function TradingPanelSidebar({
  eventSlug,
  outcomes,
}: {
  eventSlug: string;
  outcomes: Outcome[];
}) {
  return (
    <div className="space-y-4">
      {/* Trading Panel - sticky on desktop, collapsible on mobile */}
      <TradingPanel eventSlug={eventSlug} outcomes={outcomes} />

      {/* Market Stats Card */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Clock className="h-4 w-4 text-gray-400" />
            Market Info
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SectionPlaceholder
            title="Market Statistics"
            description="Volume, liquidity, participants"
            minHeight="min-h-[100px]"
          />
        </CardContent>
      </Card>

      {/* Related Events Card */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Related Events</CardTitle>
        </CardHeader>
        <CardContent>
          <SectionPlaceholder
            title="Related Events"
            description="Similar markets in this category"
            minHeight="min-h-[80px]"
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default function EventDetailPage({ params }: EventPageProps) {
  // Unwrap the params promise (Next.js 15 pattern)
  const { slug } = use(params);

  const {
    data: event,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useEvent(slug);

  // Update page title when event is loaded
  useEffect(() => {
    if (event?.title) {
      document.title = `${event.title} | PredMkts`;
    }
    return () => {
      // Reset to default title when leaving the page
      document.title = 'PredMkts';
    };
  }, [event?.title]);

  // Loading state
  if (isLoading) {
    return <EventDetailPageSkeleton />;
  }

  // Error state - check if it's a 404 (Event not found)
  if (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    const isNotFound = errorMessage.toLowerCase().includes('not found');

    // Use dedicated EventNotFound component for 404s
    if (isNotFound) {
      return <EventNotFound slug={slug} />;
    }

    // Use EventError for other errors
    return (
      <EventError
        message={errorMessage}
        onRetry={() => refetch()}
        isRetrying={isFetching}
      />
    );
  }

  // No data (shouldn't happen if no error, but handle gracefully)
  if (!event) {
    return <EventNotFound slug={slug} />;
  }

  // Build breadcrumb items
  const breadcrumbs = [
    { label: 'Markets', href: '/markets' },
    ...(event.category ? [{ label: event.category, href: `/markets?category=${encodeURIComponent(event.category)}` }] : []),
    { label: event.title },
  ];

  // Extract outcomes from the first market for the trading panel
  // For events with multiple markets, we show the first market's outcomes
  const tradingOutcomes: Outcome[] = (event.markets?.[0]?.outcomes ?? []).map((outcome) => ({
    id: outcome.id,
    tokenId: outcome.tokenId,
    outcomeName: outcome.outcomeName,
    currentPrice: outcome.currentPrice,
  }));

  return (
    <EventDetailLayout
      breadcrumbs={breadcrumbs}
      sidebar={<TradingPanelSidebar eventSlug={slug} outcomes={tradingOutcomes} />}
    >
      {/* Event Header */}
      <EventHeader
        title={event.title}
        description={event.description}
        category={event.category}
        status={event.status}
      />

      {/* Outcomes / Markets */}
      <OutcomesList markets={event.markets ?? []} />

      {/* Price Chart Placeholder */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Price History</CardTitle>
        </CardHeader>
        <CardContent>
          <SectionPlaceholder
            title="Price Chart"
            description="Historical price data and trends"
            minHeight="min-h-[300px]"
          />
        </CardContent>
      </Card>

      {/* Activity Tabs - Comments, Top Holders, Activity Feed */}
      <ActivityTabs
        defaultTab="activity"
        conditionId={event.markets?.[0]?.id}
      />
    </EventDetailLayout>
  );
}
