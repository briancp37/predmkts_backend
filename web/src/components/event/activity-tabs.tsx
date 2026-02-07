/**
 * Activity Tabs Component
 *
 * Sprint 05 - Activity and Social
 * PRD: activity_tabs
 *
 * Features:
 * - Tabbed container for Comments, Top Holders, Activity content
 * - URL hash or state for active tab persistence
 * - Smooth transitions between tab content
 * - Count badge on Activity tab for recent trades
 * - Responsive/scrollable tabs on mobile
 */

'use client';

import * as React from 'react';
import * as Tabs from '@radix-ui/react-tabs';
import { MessageCircle, Users, Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';

export type TabValue = 'comments' | 'holders' | 'activity';

export interface ActivityTabsProps {
  /** Optional default tab to show */
  defaultTab?: TabValue;
  /** Recent activity count for badge display */
  activityCount?: number;
  /** Condition ID for fetching market-specific data */
  conditionId?: string;
  /** Optional className for the container */
  className?: string;
}

interface TabConfig {
  value: TabValue;
  label: string;
  icon: React.ReactNode;
}

const tabs: TabConfig[] = [
  { value: 'comments', label: 'Comments', icon: <MessageCircle className="h-4 w-4" /> },
  { value: 'holders', label: 'Top Holders', icon: <Users className="h-4 w-4" /> },
  { value: 'activity', label: 'Activity', icon: <Activity className="h-4 w-4" /> },
];

/**
 * ActivityTabs - Tabbed container for social/activity content
 */
export function ActivityTabs({
  defaultTab = 'activity',
  activityCount,
  conditionId,
  className,
}: ActivityTabsProps) {
  const [activeTab, setActiveTab] = React.useState<TabValue>(defaultTab);

  // Sync with URL hash on mount and hash changes
  React.useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '') as TabValue;
      if (tabs.some((t) => t.value === hash)) {
        setActiveTab(hash);
      }
    };

    // Check initial hash
    handleHashChange();

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  // Update URL hash when tab changes
  const handleTabChange = (value: string) => {
    const newTab = value as TabValue;
    setActiveTab(newTab);
    // Update URL hash without scrolling
    window.history.replaceState(null, '', `#${newTab}`);
  };

  return (
    <Card className={cn('overflow-hidden', className)}>
      <Tabs.Root value={activeTab} onValueChange={handleTabChange}>
        {/* Tab List - scrollable on mobile */}
        <div className="border-b border-gray-200">
          <Tabs.List
            className="flex overflow-x-auto scrollbar-hide"
            aria-label="Activity sections"
          >
            {tabs.map((tab) => (
              <Tabs.Trigger
                key={tab.value}
                value={tab.value}
                className={cn(
                  'flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap',
                  'border-b-2 transition-colors duration-200',
                  'hover:text-gray-900 hover:bg-gray-50',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2',
                  'data-[state=active]:border-indigo-600 data-[state=active]:text-indigo-600',
                  'data-[state=inactive]:border-transparent data-[state=inactive]:text-gray-500'
                )}
              >
                {tab.icon}
                <span>{tab.label}</span>
                {/* Activity count badge */}
                {tab.value === 'activity' && activityCount !== undefined && activityCount > 0 && (
                  <span className="ml-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-semibold rounded-full bg-indigo-100 text-indigo-700">
                    {activityCount > 99 ? '99+' : activityCount}
                  </span>
                )}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </div>

        {/* Tab Content with transitions */}
        <CardContent className="p-0">
          <Tabs.Content
            value="comments"
            className="p-6 focus:outline-none data-[state=inactive]:hidden"
          >
            <CommentsPlaceholder />
          </Tabs.Content>

          <Tabs.Content
            value="holders"
            className="p-6 focus:outline-none data-[state=inactive]:hidden"
          >
            <TopHoldersPlaceholder conditionId={conditionId} />
          </Tabs.Content>

          <Tabs.Content
            value="activity"
            className="p-6 focus:outline-none data-[state=inactive]:hidden"
          >
            <ActivityFeedPlaceholder conditionId={conditionId} />
          </Tabs.Content>
        </CardContent>
      </Tabs.Root>
    </Card>
  );
}

/**
 * Comments Tab Placeholder
 * Will be replaced with full implementation in comments_placeholder category
 */
function CommentsPlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <MessageCircle className="h-12 w-12 text-gray-300 mb-4" />
      <h3 className="text-lg font-medium text-gray-900 mb-2">Comments Coming Soon</h3>
      <p className="text-sm text-gray-500 max-w-sm">
        Join the discussion about this market. Community features are on the way.
      </p>
    </div>
  );
}

/**
 * Top Holders Tab Placeholder
 * Will be replaced with full implementation using useTopHolders hook
 */
function TopHoldersPlaceholder({ conditionId }: { conditionId?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <Users className="h-12 w-12 text-gray-300 mb-4" />
      <h3 className="text-lg font-medium text-gray-900 mb-2">Top Holders</h3>
      <p className="text-sm text-gray-500 max-w-sm">
        {conditionId
          ? 'Loading top holders for this market...'
          : 'Select a market to view top holders.'}
      </p>
    </div>
  );
}

/**
 * Activity Feed Placeholder
 * Will be replaced with full implementation using useMarketTrades hook
 */
function ActivityFeedPlaceholder({ conditionId }: { conditionId?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <Activity className="h-12 w-12 text-gray-300 mb-4" />
      <h3 className="text-lg font-medium text-gray-900 mb-2">Recent Activity</h3>
      <p className="text-sm text-gray-500 max-w-sm">
        {conditionId
          ? 'Loading recent trades for this market...'
          : 'Select a market to view trading activity.'}
      </p>
    </div>
  );
}

export default ActivityTabs;
