/**
 * Sync Markets Metadata to ClickHouse Job API Route
 *
 * Syncs market metadata from PostgreSQL to ClickHouse markets_metadata table.
 * This enables JOINs with S3 historical trade queries to enrich trades with market info.
 *
 * POST /api/jobs/sync-markets-metadata
 * Authorization: Bearer <CRON_SECRET>
 *
 * Returns:
 * - 200: Sync completed successfully
 * - 401: Unauthorized
 * - 500: Internal server error
 */

import { NextRequest, NextResponse } from 'next/server';
import { syncMarketsMetadata } from '@/lib/jobs/sync-markets-metadata';

function isAuthorized(request: NextRequest): boolean {
  const authHeader = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;

  if (!cronSecret) {
    console.error('[sync-markets-metadata-api] CRON_SECRET not configured');
    return false;
  }

  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : authHeader;
  return token === cronSecret;
}

export async function POST(request: NextRequest) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const startTime = Date.now();

  try {
    const result = await syncMarketsMetadata();

    if (!result.success) {
      return NextResponse.json(
        {
          error: 'Sync failed',
          details: result.error,
          duration_ms: result.duration_ms,
        },
        { status: 500 }
      );
    }

    return NextResponse.json({
      success: true,
      synced: result.synced,
      duration_ms: result.duration_ms,
      executionTime: Date.now() - startTime,
    });
  } catch (error) {
    console.error(
      '[sync-markets-metadata-api] Error:',
      error instanceof Error ? error.message : error
    );

    const isDev = process.env.NODE_ENV === 'development';

    return NextResponse.json(
      {
        error: 'Sync failed',
        details: error instanceof Error ? error.message : 'Unknown error',
        ...(isDev && error instanceof Error && { stack: error.stack }),
      },
      { status: 500 }
    );
  }
}
