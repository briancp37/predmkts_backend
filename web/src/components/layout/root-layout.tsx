'use client';

import * as React from 'react';
import { Providers } from '../providers';

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
}

/**
 * Root application layout component
 * Wraps the entire application with required providers
 *
 * This component is the Vite equivalent of Next.js App Router's layout.tsx
 * It provides:
 * - AuthProvider for JWT-based authentication state
 * - React Query provider for data fetching
 */
export function RootLayout({ children }: RootLayoutProps) {
  return <Providers>{children}</Providers>;
}

export default RootLayout;
