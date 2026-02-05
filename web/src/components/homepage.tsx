import * as React from 'react';
import {
  BarChart3,
  Brain,
  Anchor,
  AlertTriangle,
  AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';

interface Feature {
  title: string;
  description: string;
  icon: React.ElementType;
  href: string;
}

const features: Feature[] = [
  {
    title: 'Analyze Markets',
    description: 'Deep dive into Polymarket data with advanced analytics and market insights.',
    icon: BarChart3,
    href: '/markets',
  },
  {
    title: 'Smart Scores',
    description: 'Identify skilled traders using our proprietary scoring algorithm.',
    icon: Brain,
    href: '/smart-scores',
  },
  {
    title: 'Whale Tracking',
    description: 'Monitor large traders and their positions across all markets.',
    icon: Anchor,
    href: '/whales',
  },
  {
    title: 'Insider Detection',
    description: 'Discover potential insider trading patterns and suspicious activity.',
    icon: AlertTriangle,
    href: '/insiders',
  },
];

export interface HomepageProps {
  className?: string;
}

export function Homepage({ className }: HomepageProps) {
  return (
    <div className={cn('min-h-screen bg-gray-50', className)}>
      {/* Hero Section */}
      <section className="px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl lg:text-6xl">
            Polymarket Intelligence
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-gray-600 sm:text-xl">
            Track smart money, analyze markets, and discover alpha on Polymarket with
            powerful analytics and real-time insights.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a
              href="/smart-scores"
              className="w-full rounded-lg bg-indigo-600 px-8 py-3 text-base font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 sm:w-auto"
            >
              View Smart Scores
            </a>
            <a
              href="/whales"
              className="text-base font-semibold text-indigo-600 hover:text-indigo-500"
            >
              Track Whales <span aria-hidden="true">→</span>
            </a>
          </div>
        </div>
      </section>

      {/* Alert Banner */}
      <section className="px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl">
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
            <div className="flex items-center gap-3">
              <AlertCircle className="h-5 w-5 flex-shrink-0 text-amber-600" />
              <p className="text-sm text-amber-800">
                <span className="font-semibold">New:</span> Potential Insiders Dashboard{' '}
                <a
                  href="/insiders"
                  className="font-medium text-amber-900 underline hover:text-amber-700"
                >
                  Check it out →
                </a>
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Cards Grid */}
      <section className="px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((feature) => (
              <FeatureCard key={feature.title} feature={feature} />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

interface FeatureCardProps {
  feature: Feature;
}

function FeatureCard({ feature }: FeatureCardProps) {
  const Icon = feature.icon;

  return (
    <a href={feature.href} className="group block">
      <Card className="h-full transition-shadow hover:shadow-md">
        <CardHeader>
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600 group-hover:bg-indigo-200">
            <Icon className="h-5 w-5" />
          </div>
          <CardTitle>{feature.title}</CardTitle>
          <CardDescription>{feature.description}</CardDescription>
        </CardHeader>
      </Card>
    </a>
  );
}
