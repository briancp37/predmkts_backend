'use client';

import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Navigation, type User } from '@/components/layout/navigation';
import { ErrorBoundary } from '@/components/error-boundary';
import { useSession, useAuth } from '@/components/providers';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: session } = useSession();
  const { logout } = useAuth();

  // Convert session user to navigation user format
  const user: User | null = session?.user
    ? {
        email: session.user.email,
        name: session.user.name ?? undefined,
        tier: session.user.tier,
      }
    : null;

  const handleSignOut = () => {
    logout();
    router.push('/login');
    router.refresh();
  };

  // Handle errors in child components
  const handleError = useCallback((error: Error, errorInfo: React.ErrorInfo) => {
    // Log error for debugging - could be sent to error tracking service
    console.error('Dashboard error:', error, errorInfo);
  }, []);

  // Reset handler for error boundary
  const handleReset = useCallback(() => {
    // Could add additional cleanup logic here
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} onSignOut={handleSignOut} />
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <ErrorBoundary onError={handleError} onReset={handleReset}>
          {children}
        </ErrorBoundary>
      </main>
    </div>
  );
}
