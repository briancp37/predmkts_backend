'use client';

import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/providers';
import { RegistrationPage } from '@/components/registration-page';
import { ApiError } from '@/lib/api/client';

export default function Page() {
  const router = useRouter();
  const { register } = useAuth();

  const handleSubmit = async (data: { name: string; email: string; password: string }) => {
    try {
      // Register and auto-login
      await register({
        email: data.email,
        password: data.password,
        name: data.name,
      });

      // Redirect to home after successful registration + login
      router.push('/');
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError) {
        throw new Error(error.detail || error.message);
      }
      throw error;
    }
  };

  return <RegistrationPage onSubmit={handleSubmit} />;
}
