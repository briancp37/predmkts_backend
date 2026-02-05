'use client';

import * as React from 'react';
import { Providers, type Session } from '../providers';

/**
 * Metadata for the application
 * In Next.js, this would be exported from layout.tsx
 * For Vite, this is provided as documentation and can be used by head managers
 */
export const metadata = {
  title: 'Polymarket Intelligence',
  description: 'Advanced analytics and intelligence for Polymarket traders',
};

export interface RootLayoutProps {
  children: React.ReactNode;
  /** Optional session for testing or SSR hydration */
  session?: Session | null;
}

/**
 * Root application layout component
 * Wraps the entire application with required providers
 *
 * This component is the Vite equivalent of Next.js App Router's layout.tsx
 * It provides:
 * - Session context for authentication (via NextAuth)
 * - React Query provider for data fetching
 */
export function RootLayout({ children, session }: RootLayoutProps) {
  return <Providers session={session}>{children}</Providers>;
}

export default RootLayout;
