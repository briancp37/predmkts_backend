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
import { Tag, Clock } from 'lucide-react';
import { useEvent } from '@/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EventDetailPageSkeleton } from '@/components/loading-skeleton';
import { EventDetailLayout, SectionPlaceholder, EventNotFound, EventError, ActivityTabs, TradingPanel, MultiMarketAccordion, type Outcome, type AccordionMarket, type MarketOutcome } from '@/components/event';
import type { EventMarketResponse } from '@/hooks';

interface EventPageProps {
  params: Promise<{ slug: string }>;
}

/**
 * Map API market response to AccordionMarket format
 */
function mapToAccordionMarkets(markets: EventMarketResponse[] | undefined): AccordionMarket[] {
  if (!markets) return [];

  return markets.map((market): AccordionMarket => ({
    id: market.id,
    question: market.question,
    outcomes: (market.outcomes ?? []).map((outcome): MarketOutcome => ({
      id: outcome.id,
      tokenId: outcome.tokenId,
      outcomeName: outcome.outcomeName,
      currentPrice: outcome.currentPrice,
      priceChange24h: outcome.priceChange24h,
    })),
    totalVolume: market.totalVolume,
    liquidity: market.liquidity,
    volume24h: market.volume24h,
    imageUrl: market.imageUrl ?? undefined,
    description: market.description ?? undefined,
    isResolved: market.resolved,
  }));
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

      {/* Expandable Market Accordion with multi-market support */}
      <MultiMarketAccordion
        markets={mapToAccordionMarkets(event.markets)}
        mode="single"
        persistToUrl
        initialDisplayCount={5}
        defaultSort="probability"
        realtimePrices={{
          enabled: true,
          refetchInterval: 10000,
          pauseWhenCollapsed: true,
        }}
      />

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
