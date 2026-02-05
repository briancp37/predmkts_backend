import * as React from 'react';
import { Navigation, User } from './navigation';
import { cn } from '@/lib/utils';

export interface DashboardLayoutProps {
  children: React.ReactNode;
  user?: User | null;
  currentPath?: string;
  onSignOut?: () => void;
  className?: string;
}

export function DashboardLayout({
  children,
  user,
  currentPath,
  onSignOut,
  className,
}: DashboardLayoutProps) {
  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentPath={currentPath} onSignOut={onSignOut} />
      <main className={cn('mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8', className)}>
        {children}
      </main>
    </div>
  );
}
