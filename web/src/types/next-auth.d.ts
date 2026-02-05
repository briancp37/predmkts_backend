/**
 * NextAuth.js Type Declarations
 *
 * Extends the default NextAuth types to include custom user properties.
 */

import 'next-auth';
import 'next-auth/jwt';

declare module 'next-auth' {
  /**
   * Extended User interface with tier property
   */
  interface User {
    id: string;
    email: string;
    name?: string | null;
    tier?: 'FREE' | 'PRO';
  }

  /**
   * Extended Session interface with user tier
   */
  interface Session {
    user: {
      id: string;
      email: string;
      name?: string | null;
      tier: 'FREE' | 'PRO';
    };
  }
}

declare module 'next-auth/jwt' {
  /**
   * Extended JWT interface with user properties
   */
  interface JWT {
    id: string;
    tier: 'FREE' | 'PRO';
  }
}
