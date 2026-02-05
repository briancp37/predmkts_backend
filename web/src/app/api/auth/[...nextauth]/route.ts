/**
 * NextAuth.js API Route Handler
 *
 * PRD #22 - Create NextAuth API route handler
 *
 * This route handles all authentication endpoints:
 * - /api/auth/signin - Sign in with credentials
 * - /api/auth/signout - Sign out
 * - /api/auth/session - Get current session
 * - /api/auth/csrf - Get CSRF token
 * - /api/auth/providers - Get configured providers
 * - /api/auth/callback/:provider - OAuth callback (not used with credentials)
 */

import NextAuth from 'next-auth';
import type { NextAuthOptions } from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';
import { PrismaAdapter } from '@auth/prisma-adapter';
import type { Adapter } from 'next-auth/adapters';
import { prisma } from '@/lib/prisma';
import { authenticateUser, AuthError } from '@/lib/auth';

/**
 * NextAuth configuration options
 *
 * PRD #19 - Configure NextAuth with credentials provider
 * PRD #20 - Implement credential authorization logic
 * PRD #21 - Configure NextAuth JWT callbacks
 */
export const authOptions: NextAuthOptions = {
  // Use Prisma adapter for database session storage
  // Note: When using credentials provider with JWT strategy,
  // the adapter is primarily used for storing users, not sessions
  adapter: PrismaAdapter(prisma) as Adapter,

  // Configure session to use JWT strategy (PRD #19)
  session: {
    strategy: 'jwt',
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },

  // Configure custom auth pages (PRD #19)
  pages: {
    signIn: '/login',
    newUser: '/register',
    error: '/login',
  },

  // Configure authentication providers
  providers: [
    // Credentials provider for email/password authentication (PRD #19)
    CredentialsProvider({
      name: 'Credentials',
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      /**
       * Authorize function for credential validation
       *
       * PRD #20 - Implement credential authorization logic:
       * - Validate that email and password are provided
       * - Query user by email from database
       * - Compare provided password with stored hash using bcrypt
       * - Return user object with id, email, name, and tier on success
       * - Throw error with message 'Invalid credentials' on failure
       */
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          throw new Error('Email and password are required');
        }

        try {
          const result = await authenticateUser({
            email: credentials.email,
            password: credentials.password,
          });

          // Return user object for JWT token
          return {
            id: result.user.id,
            email: result.user.email,
            name: result.user.name,
            tier: result.user.tier,
          };
        } catch (error) {
          if (error instanceof AuthError) {
            throw new Error(error.message);
          }
          throw new Error('An error occurred during authentication');
        }
      },
    }),
  ],

  // Configure callbacks (PRD #21)
  callbacks: {
    /**
     * JWT callback - Add user id and tier to token
     *
     * PRD #21 - Implement jwt callback to add user id and tier to token
     */
    async jwt({ token, user }) {
      if (user) {
        token.id = user.id;
        token.tier = ((user as { tier?: string }).tier || 'FREE') as 'FREE' | 'PRO';
      }
      return token;
    },

    /**
     * Session callback - Add id and tier to session.user
     *
     * PRD #21 - Implement session callback to add id and tier to session.user
     */
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id as string;
        session.user.tier = token.tier as 'FREE' | 'PRO';
      }
      return session;
    },
  },

  // Enable debug mode in development
  debug: process.env.NODE_ENV === 'development',
};

// Create the NextAuth handler
const handler = NextAuth(authOptions);

// Export as GET and POST handlers for App Router (PRD #22)
export { handler as GET, handler as POST };
