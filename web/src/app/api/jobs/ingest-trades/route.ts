/**
 * Trade Ingestion Job API Route
 *
 * PRD #5 - Create API route to control trade ingestion job
 *
 * Handles POST requests to /api/jobs/ingest-trades with:
 * - CRON_SECRET authorization via Authorization header
 * - Body: { action: 'start' | 'stop' | 'status' }
 *
 * Returns:
 * - 200: Action completed successfully
 * - 400: Invalid action
 * - 401: Unauthorized (missing or invalid CRON_SECRET)
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { tradeIngestor } from '@/lib/jobs/ingest-trades';

/**
 * Verify CRON_SECRET authorization
 */
function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[ingest-trades-api] CRON_SECRET not configured');
    return false;
  }

  // Support both "Bearer <token>" and direct token
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;

  return token === cronSecret;
}

/**
 * Request body interface
 */
interface RequestBody {
  action: 'start' | 'stop' | 'status';
}

/**
 * POST /api/jobs/ingest-trades
 *
 * Controls the trade ingestion job (start/stop/status)
 */
export async function POST(request: NextRequest) {
  // Verify authorization
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    // Parse request body
    const body: RequestBody = await request.json();
    const { action } = body;

    // Validate action
    if (!action || !['start', 'stop', 'status'].includes(action)) {
      return NextResponse.json(
        { error: 'Invalid action. Must be one of: start, stop, status' },
        { status: 400 }
      );
    }

    // Handle actions
    switch (action) {
      case 'start': {
        await tradeIngestor.start();
        return NextResponse.json({
          success: true,
          message: 'Ingestion started',
        });
      }

      case 'stop': {
        await tradeIngestor.stop();
        return NextResponse.json({
          success: true,
          message: 'Ingestion stopped',
        });
      }

      case 'status': {
        const status = tradeIngestor.status();
        return NextResponse.json({
          status: {
            mode: status.mode,
            trades_count: status.tradesIngested,
            last_trade: status.lastTradeAt,
            uptime: status.connectedSince
              ? Math.floor((Date.now() - new Date(status.connectedSince).getTime()) / 1000)
              : null,
            reconnect_attempts: status.reconnectAttempts,
            is_running: status.isRunning,
            rest_poll_info: status.restPollInfo,
          },
        });
      }

      default:
        return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
    }
  } catch (error) {
    console.error('[ingest-trades-api] Error:', error instanceof Error ? error.message : error);

    return NextResponse.json(
      {
        error: 'Operation failed',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
