'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/components/providers';
import { LoginPage } from '@/components/login-page';
import { ApiError } from '@/lib/api/client';

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();

  const handleSubmit = async (data: { email: string; password: string }) => {
    try {
      await login({
        email: data.email,
        password: data.password,
      });

      // Redirect to callback URL or home
      const callbackUrl = searchParams.get('callbackUrl') || '/';
      router.push(callbackUrl);
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError) {
        throw new Error(error.detail || error.message);
      }
      throw error;
    }
  };

  return <LoginPage onSubmit={handleSubmit} />;
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <LoginContent />
    </Suspense>
  );
}
