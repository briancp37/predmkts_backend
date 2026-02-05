'use client';

import { useRouter } from 'next/navigation';
import { Navigation, type User } from '@/components/layout/navigation';
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

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} onSignOut={handleSignOut} />
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
    </div>
  );
}
