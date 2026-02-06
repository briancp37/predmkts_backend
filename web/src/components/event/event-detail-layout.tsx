/**
 * Event Detail Layout Component
 *
 * Sprint 01 - Event Page Foundation
 * PRD: page_layout
 *
 * Features:
 * - Two-column layout: main content + sidebar
 * - Responsive: single column on mobile, two columns on desktop
 * - Sticky sidebar on desktop (position: sticky)
 * - Placeholder sections for component areas
 */

'use client';

import * as React from 'react';
import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export interface EventDetailLayoutProps {
  /** Breadcrumb items for navigation */
  breadcrumbs: BreadcrumbItem[];
  /** Main content area - event header, outcomes, chart, activity */
  children: React.ReactNode;
  /** Sidebar content - trading panel, related events */
  sidebar?: React.ReactNode;
  /** Additional CSS classes for the container */
  className?: string;
}

/**
 * Breadcrumb Navigation
 * Displays: Markets > Category > Event Title
 */
function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="flex items-center text-sm text-gray-500" aria-label="Breadcrumb">
      <ol className="flex items-center space-x-1">
        {items.map((item, index) => (
          <li key={index} className="flex items-center">
            {index > 0 && (
              <ChevronRight className="mx-1 h-4 w-4 flex-shrink-0 text-gray-400" />
            )}
            {item.href ? (
              <Link
                href={item.href}
                className="hover:text-gray-700 hover:underline transition-colors"
              >
                {item.label}
              </Link>
            ) : (
              <span className="font-medium text-gray-900 truncate max-w-[200px] md:max-w-none">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/**
 * EventDetailLayout Component
 *
 * Two-column layout with main content and sticky sidebar.
 * Collapses to single column on mobile.
 */
export function EventDetailLayout({
  breadcrumbs,
  children,
  sidebar,
  className,
}: EventDetailLayoutProps) {
  return (
    <div className={cn('space-y-4', className)}>
      {/* Breadcrumb Navigation */}
      <Breadcrumbs items={breadcrumbs} />

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main Content - Takes up 2/3 on desktop */}
        <main className="lg:col-span-2 space-y-6">
          {children}
        </main>

        {/* Sidebar - Takes up 1/3 on desktop, sticky */}
        {sidebar && (
          <aside className="lg:col-span-1">
            <div className="lg:sticky lg:top-24 space-y-6">
              {sidebar}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

/**
 * Placeholder component for sections under development
 */
export function SectionPlaceholder({
  title,
  description,
  minHeight = 'min-h-[200px]',
  className,
}: {
  title: string;
  description?: string;
  minHeight?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 flex flex-col items-center justify-center text-center',
        minHeight,
        className
      )}
    >
      <div className="text-sm font-medium text-gray-500">{title}</div>
      {description && (
        <div className="mt-1 text-xs text-gray-400">{description}</div>
      )}
    </div>
  );
}

export default EventDetailLayout;
