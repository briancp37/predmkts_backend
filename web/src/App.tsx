import { RootLayout } from './components/layout/root-layout';
import { DashboardLayout } from './components/layout/dashboard-layout';
import { Homepage } from './components/homepage';
import { useSession, useAuth } from './components/providers';
import type { User } from './components/layout/navigation';

/**
 * Main application component (Vite demo - not used by Next.js)
 */
export function App() {
  const { data: session } = useSession();
  const { logout } = useAuth();

  // Convert session user to navigation user format
  const navUser: User | null = session?.user
    ? {
        email: session.user.email ?? '',
        name: session.user.name ?? undefined,
        tier: (session.user as { tier?: 'FREE' | 'PRO' }).tier ?? 'FREE',
      }
    : null;

  // Handle sign out
  const handleSignOut = () => {
    logout();
  };

  return (
    <RootLayout>
      <DashboardLayout user={navUser} currentPath="/" onSignOut={handleSignOut}>
        <Homepage />
      </DashboardLayout>
    </RootLayout>
  );
}
