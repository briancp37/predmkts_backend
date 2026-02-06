/**
 * MSW request handlers for API mocking
 *
 * Provides mock implementations for all API endpoints used in tests.
 * Handlers can be overridden in individual tests using server.use().
 */

import { http, HttpResponse } from 'msw';

const API_BASE = '/api/v1';

// Test data
export const mockUser = {
  id: 'test-user-id',
  email: 'test@example.com',
  name: 'Test User',
  tier: 'FREE' as const,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

export const mockTokens = {
  access_token: 'mock-access-token',
  refresh_token: 'mock-refresh-token',
  token_type: 'bearer',
};

export const mockMarket = {
  id: '0x1234567890123456789012345678901234567890123456789012345678901234',
  question: 'Will Bitcoin reach $100k by end of 2024?',
  description: 'This market resolves YES if Bitcoin reaches $100,000 USD.',
  category: 'Crypto',
  outcomes: [
    { name: 'Yes', price: 0.45 },
    { name: 'No', price: 0.55 },
  ],
  volume: 1250000,
  liquidity: 500000,
  end_date: '2024-12-31T23:59:59Z',
  image: null,
  active: true,
};

export const mockMarkets = [
  mockMarket,
  {
    ...mockMarket,
    id: '0x2345678901234567890123456789012345678901234567890123456789012345',
    question: 'Will ETH 2.0 launch successfully?',
    category: 'Crypto',
    outcomes: [
      { name: 'Yes', price: 0.78 },
      { name: 'No', price: 0.22 },
    ],
  },
  {
    ...mockMarket,
    id: '0x3456789012345678901234567890123456789012345678901234567890123456',
    question: 'Will Democrats win the 2024 election?',
    category: 'Politics',
    outcomes: [
      { name: 'Yes', price: 0.52 },
      { name: 'No', price: 0.48 },
    ],
  },
];

export const mockWatchlistItem = {
  id: 'watchlist-item-1',
  marketId: mockMarket.id,
  userId: mockUser.id,
  createdAt: '2024-01-01T00:00:00Z',
  market: mockMarket,
};

export const handlers = [
  // Auth handlers
  http.post(`${API_BASE}/auth/register`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const email = body.email as string;

    // Simulate duplicate email error
    if (email === 'existing@example.com') {
      return HttpResponse.json(
        { detail: 'Email already registered', code: 'DUPLICATE_ERROR', status: 400 },
        { status: 400 }
      );
    }

    // Simulate validation error for weak password
    const password = body.password as string;
    if (password && password.length < 8) {
      return HttpResponse.json(
        {
          detail: 'Validation error',
          code: 'VALIDATION_ERROR',
          status: 422,
          errors: [
            { loc: ['body', 'password'], msg: 'Password must be at least 8 characters' },
          ],
        },
        { status: 422 }
      );
    }

    return HttpResponse.json({
      ...mockUser,
      email,
      name: body.name || null,
    });
  }),

  http.post(`${API_BASE}/auth/login`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const email = body.email as string;
    const password = body.password as string;

    // Simulate invalid credentials
    if (email === 'wrong@example.com' || password === 'wrongpassword') {
      return HttpResponse.json(
        { detail: 'Invalid email or password', code: 'AUTHENTICATION_FAILED', status: 401 },
        { status: 401 }
      );
    }

    return HttpResponse.json(mockTokens);
  }),

  http.get(`${API_BASE}/auth/me`, ({ request }) => {
    const authHeader = request.headers.get('Authorization');

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json(
        { detail: 'Not authenticated', code: 'AUTHENTICATION_FAILED', status: 401 },
        { status: 401 }
      );
    }

    return HttpResponse.json(mockUser);
  }),

  http.post(`${API_BASE}/auth/refresh`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const refreshToken = body.refresh_token as string;

    if (refreshToken === 'invalid-refresh-token') {
      return HttpResponse.json(
        { detail: 'Invalid refresh token', code: 'AUTHENTICATION_FAILED', status: 401 },
        { status: 401 }
      );
    }

    return HttpResponse.json({
      ...mockTokens,
      access_token: 'new-access-token',
      refresh_token: 'new-refresh-token',
    });
  }),

  // Markets handlers
  http.get(`${API_BASE}/markets`, ({ request }) => {
    const url = new URL(request.url);
    const category = url.searchParams.get('category');
    const search = url.searchParams.get('search');
    const limit = parseInt(url.searchParams.get('limit') || '50');
    const offset = parseInt(url.searchParams.get('offset') || '0');

    let filtered = [...mockMarkets];

    if (category) {
      filtered = filtered.filter((m) => m.category === category);
    }

    if (search) {
      const searchLower = search.toLowerCase();
      filtered = filtered.filter((m) =>
        m.question.toLowerCase().includes(searchLower)
      );
    }

    return HttpResponse.json({
      items: filtered.slice(offset, offset + limit),
      total: filtered.length,
      limit,
      offset,
    });
  }),

  http.get(`${API_BASE}/markets/:marketId`, ({ params }) => {
    const marketId = params.marketId as string;
    const market = mockMarkets.find((m) => m.id === marketId);

    if (!market) {
      return HttpResponse.json(
        { detail: 'Market not found', code: 'NOT_FOUND', status: 404 },
        { status: 404 }
      );
    }

    return HttpResponse.json(market);
  }),

  http.get(`${API_BASE}/markets/tags`, () => {
    return HttpResponse.json([
      { name: 'Crypto', count: 150 },
      { name: 'Politics', count: 120 },
      { name: 'Sports', count: 80 },
      { name: 'Entertainment', count: 45 },
    ]);
  }),

  // Watchlist handlers
  http.get(`${API_BASE}/watchlist`, ({ request }) => {
    const authHeader = request.headers.get('Authorization');

    if (!authHeader) {
      return HttpResponse.json(
        { detail: 'Not authenticated', code: 'AUTHENTICATION_FAILED', status: 401 },
        { status: 401 }
      );
    }

    return HttpResponse.json({
      items: [mockWatchlistItem],
      total: 1,
    });
  }),

  http.post(`${API_BASE}/watchlist`, async ({ request }) => {
    const authHeader = request.headers.get('Authorization');

    if (!authHeader) {
      return HttpResponse.json(
        { detail: 'Not authenticated', code: 'AUTHENTICATION_FAILED', status: 401 },
        { status: 401 }
      );
    }

    const body = (await request.json()) as Record<string, unknown>;
    const marketId = body.marketId as string;

    // Simulate duplicate
    if (marketId === 'already-in-watchlist') {
      return HttpResponse.json(
        { detail: 'Market already in watchlist', code: 'DUPLICATE_ERROR', status: 400 },
        { status: 400 }
      );
    }

    return HttpResponse.json({
      id: 'new-watchlist-item',
      marketId,
      userId: mockUser.id,
      createdAt: new Date().toISOString(),
    });
  }),

  http.delete(`${API_BASE}/watchlist/:marketId`, ({ request, params }) => {
    const authHeader = request.headers.get('Authorization');

    if (!authHeader) {
      return HttpResponse.json(
        { detail: 'Not authenticated', code: 'AUTHENTICATION_FAILED', status: 401 },
        { status: 401 }
      );
    }

    const marketId = params.marketId as string;

    if (marketId === 'not-in-watchlist') {
      return HttpResponse.json(
        { detail: 'Market not in watchlist', code: 'NOT_FOUND', status: 404 },
        { status: 404 }
      );
    }

    return new HttpResponse(null, { status: 204 });
  }),

  // Error simulation handlers (can be used to test error states)
  http.get(`${API_BASE}/error/500`, () => {
    return HttpResponse.json(
      { detail: 'Internal server error', code: 'INTERNAL_ERROR', status: 500 },
      { status: 500 }
    );
  }),

  http.get(`${API_BASE}/error/429`, () => {
    return HttpResponse.json(
      {
        detail: 'Rate limit exceeded',
        code: 'RATE_LIMIT_EXCEEDED',
        status: 429,
        retry_after: 60,
      },
      {
        status: 429,
        headers: { 'Retry-After': '60' },
      }
    );
  }),
];
