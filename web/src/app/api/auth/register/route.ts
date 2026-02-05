/**
 * User Registration API Route
 *
 * PRD #23 - Implement user registration API endpoint
 *
 * Handles POST requests to /api/auth/register with:
 * - email (required, valid email format)
 * - password (required, minimum 8 characters)
 * - name (optional)
 *
 * Returns:
 * - 201: User created successfully with id, email, name
 * - 400: Validation error (invalid email, short password)
 * - 409: Email already exists
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { registerUser, AuthError } from '@/lib/auth';

/**
 * Zod schema for registration request validation
 * PRD #23: Define Zod schema for email (valid email), password (min 8 chars), name (optional)
 */
const registerSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  name: z.string().optional(),
});

/**
 * POST /api/auth/register
 *
 * Creates a new user account
 */
export async function POST(request: NextRequest) {
  try {
    // Parse request body
    const body = await request.json();

    // Validate request body with Zod schema
    const validationResult = registerSchema.safeParse(body);

    if (!validationResult.success) {
      // Return first validation error
      const errorMessage = validationResult.error.issues[0]?.message || 'Validation error';
      return NextResponse.json({ error: errorMessage }, { status: 400 });
    }

    const { email, password, name } = validationResult.data;

    // Register user using auth library
    const result = await registerUser({ email, password, name });

    // Return success response with user data (PRD #23)
    return NextResponse.json(
      {
        id: result.user.id,
        email: result.user.email,
        name: result.user.name,
      },
      { status: 201 }
    );
  } catch (error) {
    // Handle known auth errors (PRD #23)
    if (error instanceof AuthError) {
      if (error.code === 'EMAIL_EXISTS') {
        return NextResponse.json({ error: error.message }, { status: 409 });
      }
      if (error.code === 'VALIDATION_ERROR') {
        return NextResponse.json({ error: error.message }, { status: 400 });
      }
    }

    // Log unexpected errors in development
    if (process.env.NODE_ENV === 'development') {
      console.error('Registration error:', error);
    }

    // Return generic error for unexpected failures
    return NextResponse.json({ error: 'An error occurred during registration' }, { status: 500 });
  }
}
