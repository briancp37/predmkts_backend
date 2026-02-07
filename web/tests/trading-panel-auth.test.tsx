/**
 * Trading Panel Authentication Gate Tests
 *
 * Tests for authentication gating in the TradingPanel component:
 * - Loading state while checking auth
 * - Login prompt for unauthenticated users
 * - Full trading panel for authenticated users
 * - Login redirect with callback URL
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TradingPanel } from '@/components/event/trading-panel';
import { type Outcome } from '@/components/event/outcome-selector';

// Mock next/navigation
const mockUsePathname = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => mockUsePathname(),
}));

// Mock useAuth hook from providers
const mockUseAuth = vi.fn();
vi.mock('@/components/providers', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockOutcomes: Outcome[] = [
  {
    id: 'outcome-yes',
    tokenId: '123456789',
    outcomeName: 'Yes',
    currentPrice: 0.65,
  },
  {
    id: 'outcome-no',
    tokenId: '987654321',
    outcomeName: 'No',
    currentPrice: 0.35,
  },
];

const mockUser = {
  id: 'user-123',
  email: 'test@example.com',
  name: 'Test User',
  tier: 'FREE' as const,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe('TradingPanel Authentication Gate', () => {
  beforeEach(() => {
    // Default mock values
    mockUsePathname.mockReturnValue('/event/test-event');
    mockUseAuth.mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ============================================================================
  // Loading State Tests
  // ============================================================================

  describe('Loading State', () => {
    it('shows loading spinner while checking authentication', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(
        screen.getByRole('status', { name: 'Loading authentication status' })
      ).toBeInTheDocument();
    });

    it('loading state has screen reader text', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Checking authentication...')).toBeInTheDocument();
    });

    it('does not show login prompt or trading panel while loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.queryByTestId('login-prompt')).not.toBeInTheDocument();
      expect(screen.queryByText('Select Outcome')).not.toBeInTheDocument();
    });
  });

  // ============================================================================
  // Unauthenticated State Tests
  // ============================================================================

  describe('Unauthenticated State', () => {
    it('shows login prompt for unauthenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByTestId('login-prompt')).toBeInTheDocument();
      // Check for heading text - there are two "Log in to trade" (heading and button)
      expect(screen.getByRole('heading', { name: 'Log in to trade' })).toBeInTheDocument();
    });

    it('shows login button with correct text', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByTestId('login-to-trade-button')).toHaveTextContent(
        'Log in to trade'
      );
    });

    it('login button links to login page with callback URL', () => {
      mockUsePathname.mockReturnValue('/event/my-cool-event');
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="my-cool-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      const loginButton = screen.getByTestId('login-to-trade-button');
      expect(loginButton).toHaveAttribute(
        'href',
        '/login?callbackUrl=%2Fevent%2Fmy-cool-event'
      );
    });

    it('shows descriptive text for login prompt', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(
        screen.getByText(
          'Create an account or log in to start trading on this market'
        )
      ).toBeInTheDocument();
    });

    it('shows Polymarket link as fallback for unauthenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      const polymarketLink = screen.getByText('Trade on Polymarket');
      expect(polymarketLink).toHaveAttribute(
        'href',
        'https://polymarket.com/event/test-event'
      );
      expect(polymarketLink).toHaveAttribute('target', '_blank');
      expect(polymarketLink).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('does not show outcome selector for unauthenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.queryByText('Select Outcome')).not.toBeInTheDocument();
      expect(screen.queryByText('Yes')).not.toBeInTheDocument();
    });

    it('does not show trade direction toggle for unauthenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.queryByRole('radio', { name: /buy/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('radio', { name: /sell/i })).not.toBeInTheDocument();
    });
  });

  // ============================================================================
  // Authenticated State Tests
  // ============================================================================

  describe('Authenticated State', () => {
    it('shows full trading panel for authenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        isLoading: false,
        isAuthenticated: true,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      // Should show outcome selector
      expect(screen.getByText('Select Outcome')).toBeInTheDocument();
      expect(screen.getByText('Yes')).toBeInTheDocument();
      expect(screen.getByText('No')).toBeInTheDocument();
    });

    it('shows trade direction toggle for authenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        isLoading: false,
        isAuthenticated: true,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('radio', { name: /buy/i })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /sell/i })).toBeInTheDocument();
    });

    it('shows trade submit button for authenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        isLoading: false,
        isAuthenticated: true,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('button', { name: /buy/i })).toBeInTheDocument();
    });

    it('does not show login prompt for authenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        isLoading: false,
        isAuthenticated: true,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.queryByTestId('login-prompt')).not.toBeInTheDocument();
      expect(screen.queryByTestId('login-to-trade-button')).not.toBeInTheDocument();
    });

    it('shows placeholder when authenticated but no outcomes', () => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        isLoading: false,
        isAuthenticated: true,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={[]} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Trading Coming Soon')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // URL Encoding Tests
  // ============================================================================

  describe('URL Encoding', () => {
    it('properly encodes callback URL with special characters', () => {
      mockUsePathname.mockReturnValue('/event/test-event?param=value&other=123');
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      const loginButton = screen.getByTestId('login-to-trade-button');
      expect(loginButton).toHaveAttribute(
        'href',
        '/login?callbackUrl=%2Fevent%2Ftest-event%3Fparam%3Dvalue%26other%3D123'
      );
    });

    it('properly encodes callback URL with unicode characters', () => {
      mockUsePathname.mockReturnValue('/event/test-event-with-unicode-\u00e9');
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      const loginButton = screen.getByTestId('login-to-trade-button');
      // The callback URL should be properly encoded
      expect(loginButton.getAttribute('href')).toContain('/login?callbackUrl=');
    });
  });

  // ============================================================================
  // Panel Header Tests
  // ============================================================================

  describe('Panel Header', () => {
    it('always shows Trade header regardless of auth state', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Trade')).toBeInTheDocument();
    });

    it('shows Trade header for authenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: mockUser,
        isLoading: false,
        isAuthenticated: true,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Trade')).toBeInTheDocument();
    });

    it('shows Trade header during loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Trade')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Accessibility Tests
  // ============================================================================

  describe('Accessibility', () => {
    it('login button is a proper link element', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      const loginButton = screen.getByTestId('login-to-trade-button');
      expect(loginButton.tagName).toBe('A');
    });

    it('loading spinner has role="status"', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('loading spinner has aria-label', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        isAuthenticated: false,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        refreshUser: vi.fn(),
      });

      render(<TradingPanel eventSlug="test-event" outcomes={mockOutcomes} />, {
        wrapper: createWrapper(),
      });

      expect(
        screen.getByRole('status', { name: 'Loading authentication status' })
      ).toBeInTheDocument();
    });
  });
});
