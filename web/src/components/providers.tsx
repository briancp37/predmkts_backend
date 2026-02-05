'use client';

import { useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useSession, useAuth } from '@/lib/api/auth-context';
import type { User } from '@/lib/api/auth-context';

// Re-export auth hooks for convenience
export { useSession, useAuth, type User };

/**
 * User type for session context
 */
export interface SessionUser {
  id: string;
  email: string;
  name?: string | null;
  tier: 'FREE' | 'PRO';
}

/**
 * Session type for components expecting next-auth-like interface
 */
export interface Session {
  user: SessionUser;
  expires: string;
}

/**
 * Props for Providers component
 */
interface ProvidersProps {
  children: ReactNode;
}

/**
 * Application providers wrapper component
 * Wraps children with all required providers:
 * - AuthProvider for JWT-based authentication state
 * - QueryClientProvider for data fetching with React Query
 */
export function Providers({ children }: ProvidersProps) {
  // Initialize QueryClient with useState to prevent SSR issues
  // This ensures a new client is created for each request on the server
  // but reuses the same client on the client side
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Default stale time of 60 seconds
            staleTime: 60 * 1000,
            // Don't refetch on window focus by default
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <AuthProvider>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </AuthProvider>
  );
}

export default Providers;
