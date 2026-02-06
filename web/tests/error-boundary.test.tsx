/**
 * Error boundary and error display component tests
 *
 * Tests the error handling UI components:
 * - ErrorBoundary class component
 * - ApiErrorDisplay component for different status codes
 * - InlineError component
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary, ApiErrorDisplay, InlineError } from '@/components/error-boundary';
import { ApiError } from '@/lib/api/client';

describe('ApiErrorDisplay', () => {
  it('displays 401 unauthorized error with login button', () => {
    const error = new ApiError('Session expired', 401);
    const onLogin = vi.fn();

    render(<ApiErrorDisplay error={error} onLogin={onLogin} />);

    expect(screen.getByText(/session expired/i)).toBeInTheDocument();
    expect(screen.getByText(/please log in again/i)).toBeInTheDocument();

    const loginButton = screen.getByRole('button', { name: /log in/i });
    expect(loginButton).toBeInTheDocument();

    fireEvent.click(loginButton);
    expect(onLogin).toHaveBeenCalled();
  });

  it('displays 403 forbidden error with upgrade prompt', () => {
    const error = new ApiError('Tier limit exceeded', 403);

    render(<ApiErrorDisplay error={error} />);

    expect(screen.getByText(/access restricted/i)).toBeInTheDocument();
    // Multiple elements contain "upgrade to pro" text, use getByRole for the link
    expect(screen.getByRole('link', { name: /upgrade to pro/i })).toHaveAttribute(
      'href',
      '/upgrade'
    );
    expect(screen.getByText(/reached your plan limit/i)).toBeInTheDocument();
  });

  it('displays 403 error with generic permission message when not tier-related', () => {
    const error = new ApiError('Permission denied', 403);

    render(<ApiErrorDisplay error={error} />);

    expect(screen.getByText(/access restricted/i)).toBeInTheDocument();
    expect(screen.getByText(/do not have permission/i)).toBeInTheDocument();
  });

  it('displays 404 not found error with go back button', () => {
    const error = new ApiError('Market not found', 404);
    const onRetry = vi.fn();

    render(<ApiErrorDisplay error={error} onRetry={onRetry} />);

    expect(screen.getByText(/not found/i)).toBeInTheDocument();
    expect(screen.getByText(/could not be found/i)).toBeInTheDocument();

    const goBackButton = screen.getByRole('button', { name: /go back/i });
    fireEvent.click(goBackButton);
    expect(onRetry).toHaveBeenCalled();
  });

  it('displays 429 rate limit error with retry button', () => {
    const error = new ApiError('Rate limit exceeded', 429, 'Please try again in 60 seconds.');

    render(<ApiErrorDisplay error={error} />);

    expect(screen.getByText(/too many requests/i)).toBeInTheDocument();
    expect(screen.getByText(/please wait a moment/i)).toBeInTheDocument();
  });

  it('displays 429 rate limit error with retry time from detail', () => {
    const error = new ApiError('Rate limit', 429, 'retry after 30 seconds');

    render(<ApiErrorDisplay error={error} />);

    expect(screen.getByText(/retry after 30 seconds/i)).toBeInTheDocument();
  });

  it('displays 500 server error with retry button', () => {
    const error = new ApiError('Internal server error', 500);
    const onRetry = vi.fn();

    render(<ApiErrorDisplay error={error} onRetry={onRetry} />);

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText(/servers are experiencing issues/i)).toBeInTheDocument();

    const retryButton = screen.getByRole('button', { name: /try again/i });
    fireEvent.click(retryButton);
    expect(onRetry).toHaveBeenCalled();
  });

  it('displays generic error for unknown status codes', () => {
    const error = new ApiError('Something failed', 418);

    render(<ApiErrorDisplay error={error} />);

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText(/something failed/i)).toBeInTheDocument();
  });

  it('handles non-ApiError errors', () => {
    const error = new Error('Network error');

    render(<ApiErrorDisplay error={error} />);

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    // Non-ApiError defaults to status 500, which shows the server error message
    expect(screen.getByText(/servers are experiencing issues/i)).toBeInTheDocument();
  });
});

describe('InlineError', () => {
  it('displays error message', () => {
    render(<InlineError message="Email is invalid" />);

    expect(screen.getByText(/email is invalid/i)).toBeInTheDocument();
  });

  it('displays dismiss button when onDismiss is provided', () => {
    const onDismiss = vi.fn();

    render(<InlineError message="Error message" onDismiss={onDismiss} />);

    const dismissButton = screen.getByRole('button', { name: /dismiss/i });
    fireEvent.click(dismissButton);

    expect(onDismiss).toHaveBeenCalled();
  });

  it('does not display dismiss button when onDismiss is not provided', () => {
    render(<InlineError message="Error message" />);

    expect(screen.queryByRole('button', { name: /dismiss/i })).not.toBeInTheDocument();
  });
});

describe('ErrorBoundary', () => {
  // Component that throws an error for testing
  function ThrowError({ shouldThrow }: { shouldThrow: boolean }) {
    if (shouldThrow) {
      throw new Error('Test error');
    }
    return <div>No error</div>;
  }

  // Suppress console.error for error boundary tests
  const originalConsoleError = console.error;
  beforeEach(() => {
    console.error = vi.fn();
  });
  afterEach(() => {
    console.error = originalConsoleError;
  });

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    );

    expect(screen.getByText(/child content/i)).toBeInTheDocument();
  });

  it('renders fallback UI when child throws error', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText(/unexpected error occurred/i)).toBeInTheDocument();
  });

  it('renders custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/custom fallback/i)).toBeInTheDocument();
  });

  it('calls onError callback when error occurs', () => {
    const onError = vi.fn();

    render(
      <ErrorBoundary onError={onError}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(onError).toHaveBeenCalled();
    expect(onError.mock.calls[0]?.[0]).toBeInstanceOf(Error);
    expect(onError.mock.calls[0]?.[0]?.message).toBe('Test error');
  });

  it('has Try Again button that resets error state', () => {
    const onReset = vi.fn();

    render(
      <ErrorBoundary onReset={onReset}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    const tryAgainButton = screen.getByRole('button', { name: /try again/i });
    fireEvent.click(tryAgainButton);

    expect(onReset).toHaveBeenCalled();
  });

  it('has Refresh Page button', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByRole('button', { name: /refresh page/i })).toBeInTheDocument();
  });
});
