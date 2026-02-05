/**
 * Tracked Traders Management Page
 *
 * PRD #15 (Sprint 7) - Create Tracked Traders management page with add/remove functionality
 * PRD #16 (Sprint 7) - Create Tracked Traders activity feed section
 *
 * Features:
 * - Page header with Eye icon and tier limit indicator
 * - Add Trader Card with address and custom name inputs
 * - Tracked List showing all tracked traders with actions
 * - Inline edit for custom names
 * - Delete confirmation dialog
 * - Toast notifications for actions
 * - Activity feed with 10-second auto-refresh
 * - Sound and browser notification support for new trades
 * - CSV export for activity data
 */

'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import Link from 'next/link';
import {
  Eye,
  Plus,
  Trash2,
  Edit2,
  X,
  Check,
  Copy,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Loader2,
  Activity,
  RefreshCw,
  Volume2,
  VolumeX,
  Bell,
  BellOff,
  Download,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, Column } from '@/components/ui/data-table';
import { formatCurrency, formatPercent, shortenAddress, formatDate, cn } from '@/lib/utils';

// Tier limits for display
const TIER_LIMITS = {
  FREE: 6,
  PRO: 50,
} as const;

// Trader type from tracked traders API
interface TrackedTrader {
  id: string;
  customName: string | null;
  createdAt: string;
  trader: {
    id: string;
    address: string;
    username: string | null;
    smartScore: number | null;
    totalPnl: number;
    totalTrades: number;
    winCount: number;
    lossCount: number;
    winRate: number;
  };
}

interface TrackedTradersResponse {
  trackedTraders: TrackedTrader[];
}

interface AddTraderRequest {
  traderAddress: string;
  customName?: string;
}

interface UpdateTraderRequest {
  id: string;
  customName: string | null;
}

// Activity feed types
interface ActivityTrade {
  id: string;
  trader_address: string;
  market_id: string;
  outcome_name: string;
  market_question: string;
  side: 'BUY' | 'SELL';
  price: number;
  amount: number;
  usd_value: number;
  timestamp: string;
  smart_score: number | null;
  customName: string | null;
}

interface ActivityResponse {
  trades: ActivityTrade[];
  trackedCount: number;
}

// Toast notification component
interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error';
}

/**
 * Get emoji for smart score value
 */
function getScoreEmoji(score: number | null): string {
  if (score === null) return '❓';
  if (score >= 50) return '🏆';
  if (score >= 25) return '💪';
  if (score >= 10) return '👍';
  if (score >= 0) return '😐';
  if (score >= -25) return '👎';
  return '💀';
}

/**
 * Get color class for score value
 */
function getScoreColorClass(score: number | null): string {
  if (score === null) return 'text-gray-400';
  if (score >= 50) return 'text-green-600';
  if (score >= 25) return 'text-green-500';
  if (score >= 10) return 'text-blue-500';
  if (score >= 0) return 'text-gray-500';
  if (score >= -25) return 'text-orange-500';
  return 'text-red-500';
}

/**
 * Validate Ethereum address format
 */
function isValidEthereumAddress(address: string): boolean {
  return /^0x[a-fA-F0-9]{40}$/.test(address);
}

export default function TrackedTradersPage() {
  const queryClient = useQueryClient();

  // Form state
  const [traderAddress, setTraderAddress] = useState('');
  const [customName, setCustomName] = useState('');
  const [addressError, setAddressError] = useState<string | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');

  // Delete confirmation state
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Toast notifications
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Activity feed state
  const [activityMinAmount, setActivityMinAmount] = useState(0);
  const [activityAutoRefresh, setActivityAutoRefresh] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [browserNotificationsEnabled, setBrowserNotificationsEnabled] = useState(false);
  const [notificationPermission, setNotificationPermission] =
    useState<NotificationPermission>('default');

  // Refs for sound and tracking new trades
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastTradeIdRef = useRef<string | null>(null);
  const prevTradesRef = useRef<ActivityTrade[]>([]);

  // Check notification permission on mount
  useEffect(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      setNotificationPermission(Notification.permission);
    }
  }, []);

  // Add a toast notification
  const addToast = useCallback((message: string, type: 'success' | 'error') => {
    const id = Math.random().toString(36).substring(7);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  // Remove a toast
  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Copy address to clipboard
  const copyAddress = useCallback(
    async (address: string) => {
      try {
        await navigator.clipboard.writeText(address);
        addToast('Address copied to clipboard', 'success');
      } catch {
        addToast('Failed to copy address', 'error');
      }
    },
    [addToast]
  );

  // Fetch tracked traders
  const { data, isLoading, error } = useQuery<TrackedTradersResponse>({
    queryKey: ['tracked-traders'],
    queryFn: async () => {
      const response = await fetch('/api/tracked-traders');
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Please sign in to view tracked traders');
        }
        throw new Error('Failed to fetch tracked traders');
      }
      return response.json();
    },
  });

  // Add tracked trader mutation
  const addMutation = useMutation({
    mutationFn: async ({ traderAddress, customName }: AddTraderRequest) => {
      const response = await fetch('/api/tracked-traders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          traderAddress,
          customName: customName || undefined,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to add trader');
      }

      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-traders'] });
      setTraderAddress('');
      setCustomName('');
      setAddressError(null);
      addToast('Trader added successfully', 'success');
    },
    onError: (error: Error) => {
      addToast(error.message, 'error');
    },
  });

  // Update tracked trader mutation
  const updateMutation = useMutation({
    mutationFn: async ({ id, customName }: UpdateTraderRequest) => {
      const response = await fetch(`/api/tracked-traders/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customName }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to update trader');
      }

      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-traders'] });
      setEditingId(null);
      setEditingName('');
      addToast('Trader updated successfully', 'success');
    },
    onError: (error: Error) => {
      addToast(error.message, 'error');
    },
  });

  // Delete tracked trader mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const response = await fetch(`/api/tracked-traders/${id}`, {
        method: 'DELETE',
      });

      if (!response.ok && response.status !== 204) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to remove trader');
      }

      return null;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-traders'] });
      setDeletingId(null);
      addToast('Trader removed from tracked list', 'success');
    },
    onError: (error: Error) => {
      addToast(error.message, 'error');
      setDeletingId(null);
    },
  });

  // Fetch activity feed
  const {
    data: activityData,
    isLoading: activityLoading,
    isFetching: activityFetching,
  } = useQuery<ActivityResponse>({
    queryKey: ['tracked-traders-activity', activityMinAmount],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('limit', '100');
      if (activityMinAmount > 0) {
        params.set('minAmount', activityMinAmount.toString());
      }

      const response = await fetch(`/api/tracked-traders/activity?${params.toString()}`);
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Please sign in to view activity');
        }
        throw new Error('Failed to fetch activity');
      }
      return response.json();
    },
    refetchInterval: activityAutoRefresh ? 10000 : false, // 10 second refresh when enabled
    enabled: (data?.trackedTraders?.length ?? 0) > 0, // Only fetch when there are tracked traders
  });

  // Play sound and show browser notification when new trade appears
  useEffect(() => {
    if (!activityData?.trades || activityData.trades.length === 0) return;

    const latestTradeId = activityData.trades[0]?.id;
    const latestTrade = activityData.trades[0];

    // If we have a previous trade ID and it's different from the latest
    if (lastTradeIdRef.current && latestTradeId && lastTradeIdRef.current !== latestTradeId) {
      // New trade detected - play sound
      if (soundEnabled && audioRef.current) {
        audioRef.current.play().catch(() => {
          // Ignore autoplay errors
        });
      }

      // Show browser notification
      if (browserNotificationsEnabled && notificationPermission === 'granted' && latestTrade) {
        const traderName = latestTrade.customName || shortenAddress(latestTrade.trader_address);
        const body = `${traderName} ${latestTrade.side} ${formatCurrency(latestTrade.usd_value)} on ${latestTrade.market_question.slice(0, 50)}...`;

        new Notification('New Trade Alert', {
          body,
          icon: '/icon.png',
        });
      }
    }

    // Update the ref to track the latest trade
    lastTradeIdRef.current = latestTradeId ?? null;
    prevTradesRef.current = activityData.trades;
  }, [activityData?.trades, soundEnabled, browserNotificationsEnabled, notificationPermission]);

  // Request notification permission
  const requestNotificationPermission = async () => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      const permission = await Notification.requestPermission();
      setNotificationPermission(permission);
      if (permission === 'granted') {
        setBrowserNotificationsEnabled(true);
        addToast('Browser notifications enabled', 'success');
      } else {
        addToast('Browser notifications denied', 'error');
      }
    }
  };

  // Export activity to CSV
  const exportActivityToCSV = () => {
    if (!activityData?.trades || activityData.trades.length === 0) {
      addToast('No activity data to export', 'error');
      return;
    }

    const headers = [
      'Timestamp',
      'Trader',
      'Custom Name',
      'Market',
      'Side',
      'Outcome',
      'Price',
      'Amount',
      'Smart Score',
    ];
    const rows = activityData.trades.map((trade) => [
      trade.timestamp,
      trade.trader_address,
      trade.customName || '',
      `"${trade.market_question.replace(/"/g, '""')}"`, // Escape quotes in CSV
      trade.side,
      trade.outcome_name,
      trade.price.toFixed(4),
      trade.usd_value.toFixed(2),
      trade.smart_score?.toFixed(1) || '',
    ]);

    const csvContent = [headers.join(','), ...rows.map((row) => row.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute(
      'download',
      `tracked-traders-activity-${new Date().toISOString().split('T')[0]}.csv`
    );
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    addToast('Activity exported to CSV', 'success');
  };

  // Activity table columns
  const activityColumns: Column<ActivityTrade>[] = [
    {
      key: 'timestamp',
      header: 'Time',
      render: (_, trade) => (
        <span className="text-gray-600 whitespace-nowrap">{formatDate(trade.timestamp)}</span>
      ),
      className: 'w-36',
    },
    {
      key: 'trader',
      header: 'Trader',
      render: (_, trade) => (
        <div className="flex flex-col">
          <span className="font-medium text-gray-900" title={trade.trader_address}>
            {trade.customName || shortenAddress(trade.trader_address)}
          </span>
          {trade.customName && (
            <span className="text-xs text-gray-500 font-mono">
              {shortenAddress(trade.trader_address)}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'market_question',
      header: 'Market',
      render: (_, trade) => (
        <span className="line-clamp-2 text-gray-900" title={trade.market_question}>
          {trade.market_question.length > 50
            ? `${trade.market_question.slice(0, 50)}...`
            : trade.market_question}
        </span>
      ),
    },
    {
      key: 'side',
      header: 'Side',
      render: (_, trade) => (
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2 py-1 text-xs font-medium',
            trade.side === 'BUY' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          )}
        >
          {trade.side}
        </span>
      ),
      className: 'w-16',
    },
    {
      key: 'outcome_name',
      header: 'Outcome',
      render: (_, trade) => <span className="text-gray-700">{trade.outcome_name}</span>,
      className: 'w-20',
    },
    {
      key: 'price',
      header: 'Price',
      render: (_, trade) => formatPercent(trade.price),
      className: 'text-right w-20',
    },
    {
      key: 'usd_value',
      header: 'Amount',
      render: (_, trade) => (
        <span className="font-medium text-gray-900">{formatCurrency(trade.usd_value)}</span>
      ),
      className: 'text-right w-24',
    },
  ];

  // Handle add trader form submission
  const handleAddTrader = (e: React.FormEvent) => {
    e.preventDefault();

    if (!traderAddress.trim()) {
      setAddressError('Trader address is required');
      return;
    }

    if (!isValidEthereumAddress(traderAddress.trim())) {
      setAddressError('Invalid Ethereum address format (must be 0x followed by 40 hex characters)');
      return;
    }

    setAddressError(null);
    addMutation.mutate({ traderAddress: traderAddress.trim(), customName: customName.trim() });
  };

  // Handle edit start
  const startEditing = (tracker: TrackedTrader) => {
    setEditingId(tracker.id);
    setEditingName(tracker.customName || '');
  };

  // Handle edit save
  const saveEdit = () => {
    if (editingId) {
      updateMutation.mutate({
        id: editingId,
        customName: editingName.trim() || null,
      });
    }
  };

  // Handle edit cancel
  const cancelEdit = () => {
    setEditingId(null);
    setEditingName('');
  };

  // Calculate tier info
  const trackedCount = data?.trackedTraders.length ?? 0;
  const tierLimit = TIER_LIMITS.FREE; // Default to FREE tier, would come from session in real app
  const isAtLimit = trackedCount >= tierLimit;

  // Get display name for a tracked trader
  const getDisplayName = (tracker: TrackedTrader): string => {
    if (tracker.customName) return tracker.customName;
    if (tracker.trader.username) return `@${tracker.trader.username}`;
    return shortenAddress(tracker.trader.address);
  };

  return (
    <div className="space-y-6">
      {/* Hidden audio element for notification sound */}
      <audio ref={audioRef} src="/notification.mp3" preload="auto" />

      {/* Toast Notifications */}
      <div className="fixed right-4 top-4 z-50 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              'flex items-center gap-2 rounded-lg px-4 py-3 shadow-lg',
              toast.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
            )}
          >
            <span>{toast.message}</span>
            <button
              onClick={() => removeToast(toast.id)}
              className="ml-2 rounded p-1 hover:bg-white/20"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>

      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Eye className="h-8 w-8 text-indigo-600" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Tracked Traders</h1>
            <p className="text-gray-500">
              Monitor your favorite traders and get notified of their activity
            </p>
          </div>
        </div>

        {/* Tier Limit Indicator */}
        <div className="text-right">
          <div className="text-sm text-gray-500">Tracking</div>
          <div
            className={cn('text-lg font-semibold', isAtLimit ? 'text-red-600' : 'text-gray-900')}
          >
            {trackedCount} / {tierLimit}
          </div>
        </div>
      </div>

      {/* Add Trader Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Add Trader
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAddTrader} className="space-y-4">
            <div className="flex flex-col gap-4 sm:flex-row">
              {/* Trader Address Input */}
              <div className="flex-1">
                <label htmlFor="traderAddress" className="block text-sm font-medium text-gray-700">
                  Trader Address <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="traderAddress"
                  value={traderAddress}
                  onChange={(e) => {
                    setTraderAddress(e.target.value);
                    setAddressError(null);
                  }}
                  placeholder="0x..."
                  className={cn(
                    'mt-1 w-full rounded-lg border bg-white px-4 py-2.5 font-mono text-sm text-gray-900 focus:outline-none focus:ring-1',
                    addressError
                      ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                      : 'border-gray-300 focus:border-indigo-500 focus:ring-indigo-500'
                  )}
                />
                {addressError && <p className="mt-1 text-sm text-red-600">{addressError}</p>}
              </div>

              {/* Custom Name Input */}
              <div className="flex-1">
                <label htmlFor="customName" className="block text-sm font-medium text-gray-700">
                  Custom Name <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="text"
                  id="customName"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="e.g., My Whale"
                  maxLength={50}
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {/* Submit Button */}
              <div className="flex items-end">
                <button
                  type="submit"
                  disabled={addMutation.isPending || isAtLimit}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-6 py-2.5 font-medium text-white transition-colors',
                    isAtLimit
                      ? 'cursor-not-allowed bg-gray-400'
                      : 'bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400'
                  )}
                >
                  {addMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  Add
                </button>
              </div>
            </div>

            {/* Tier Limit Warning */}
            {isAtLimit && (
              <div className="flex items-center gap-2 rounded-lg bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
                <AlertCircle className="h-5 w-5 flex-shrink-0" />
                <span>
                  You&apos;ve reached the limit for your FREE tier ({tierLimit} traders).{' '}
                  <Link
                    href="/upgrade"
                    className="font-medium text-yellow-900 underline hover:no-underline"
                  >
                    Upgrade to PRO
                  </Link>{' '}
                  to track up to {TIER_LIMITS.PRO} traders.
                </span>
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      {/* Tracked List Card */}
      <Card>
        <CardHeader>
          <CardTitle>Tracked List</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-indigo-600" />
            </div>
          ) : error ? (
            <div className="flex items-center justify-center gap-2 py-12 text-red-600">
              <AlertCircle className="h-5 w-5" />
              <span>{error instanceof Error ? error.message : 'Failed to load traders'}</span>
            </div>
          ) : !data?.trackedTraders.length ? (
            <div className="flex flex-col items-center justify-center py-12 text-gray-500">
              <Eye className="mb-4 h-12 w-12 text-gray-300" />
              <p className="text-lg font-medium">No tracked traders yet</p>
              <p className="mt-1 text-sm">Start tracking traders to see their activity</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {data.trackedTraders.map((tracker) => (
                <div key={tracker.id} className="flex items-center gap-4 py-4 first:pt-0 last:pb-0">
                  {/* Trader Info */}
                  <div className="flex-1 min-w-0">
                    {/* Name / Edit Row */}
                    <div className="flex items-center gap-2">
                      {editingId === tracker.id ? (
                        <>
                          <input
                            type="text"
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            placeholder="Custom name (optional)"
                            maxLength={50}
                            className="w-40 rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                            autoFocus
                          />
                          <button
                            onClick={saveEdit}
                            disabled={updateMutation.isPending}
                            className="rounded p-1 text-green-600 hover:bg-green-50"
                          >
                            {updateMutation.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Check className="h-4 w-4" />
                            )}
                          </button>
                          <button
                            onClick={cancelEdit}
                            disabled={updateMutation.isPending}
                            className="rounded p-1 text-gray-500 hover:bg-gray-50"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </>
                      ) : (
                        <>
                          <span className="font-medium text-gray-900 truncate">
                            {getDisplayName(tracker)}
                          </span>
                          <button
                            onClick={() => startEditing(tracker)}
                            className="rounded p-1 text-gray-400 hover:bg-gray-50 hover:text-gray-600"
                            title="Edit name"
                          >
                            <Edit2 className="h-3.5 w-3.5" />
                          </button>
                        </>
                      )}
                    </div>

                    {/* Address Row */}
                    <div className="mt-1 flex items-center gap-2">
                      <Link
                        href={`/analyze-user?address=${tracker.trader.address}`}
                        className="font-mono text-sm text-indigo-600 hover:text-indigo-800 hover:underline"
                      >
                        {shortenAddress(tracker.trader.address)}
                      </Link>
                      <button
                        onClick={() => copyAddress(tracker.trader.address)}
                        className="rounded p-1 text-gray-400 hover:bg-gray-50 hover:text-gray-600"
                        title="Copy address"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Smart Score Badge */}
                  <div className="flex items-center gap-1.5">
                    <span className="text-lg">{getScoreEmoji(tracker.trader.smartScore)}</span>
                    <span
                      className={cn('font-bold', getScoreColorClass(tracker.trader.smartScore))}
                    >
                      {tracker.trader.smartScore !== null
                        ? tracker.trader.smartScore.toFixed(1)
                        : 'N/A'}
                    </span>
                  </div>

                  {/* PnL */}
                  <div className="w-24 text-right">
                    <div className="text-xs text-gray-500">PnL</div>
                    <div
                      className={cn(
                        'flex items-center justify-end gap-1 font-medium',
                        tracker.trader.totalPnl >= 0 ? 'text-green-600' : 'text-red-600'
                      )}
                    >
                      {tracker.trader.totalPnl >= 0 ? (
                        <TrendingUp className="h-3.5 w-3.5" />
                      ) : (
                        <TrendingDown className="h-3.5 w-3.5" />
                      )}
                      {formatCurrency(tracker.trader.totalPnl)}
                    </div>
                  </div>

                  {/* Trades */}
                  <div className="w-20 text-right">
                    <div className="text-xs text-gray-500">Trades</div>
                    <div className="font-medium text-gray-900">
                      {tracker.trader.totalTrades.toLocaleString()}
                    </div>
                  </div>

                  {/* Delete Button / Confirmation */}
                  <div className="w-24 flex justify-end">
                    {deletingId === tracker.id ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => deleteMutation.mutate(tracker.id)}
                          disabled={deleteMutation.isPending}
                          className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:bg-red-400"
                        >
                          {deleteMutation.isPending ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            'Confirm'
                          )}
                        </button>
                        <button
                          onClick={() => setDeletingId(null)}
                          disabled={deleteMutation.isPending}
                          className="rounded bg-gray-200 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-300"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setDeletingId(tracker.id)}
                        className="rounded p-2 text-gray-400 hover:bg-red-50 hover:text-red-600"
                        title="Remove trader"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Activity Feed Card */}
      {trackedCount > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5" />
                Recent Activity
                {activityAutoRefresh && (
                  <span className="flex items-center gap-1.5 text-sm font-normal text-green-600">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-green-600" />
                    Live
                  </span>
                )}
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {/* Activity Controls */}
            <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-end">
              {/* Min Amount Filter */}
              <div className="flex-1">
                <label
                  htmlFor="activityMinAmount"
                  className="block text-sm font-medium text-gray-700"
                >
                  Min Amount (USD)
                </label>
                <input
                  type="number"
                  id="activityMinAmount"
                  value={activityMinAmount}
                  onChange={(e) => setActivityMinAmount(Math.max(0, Number(e.target.value)))}
                  min={0}
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {/* Auto-Refresh Toggle */}
              <div>
                <button
                  type="button"
                  onClick={() => setActivityAutoRefresh(!activityAutoRefresh)}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                    activityAutoRefresh
                      ? 'bg-green-600 text-white hover:bg-green-700'
                      : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                  )}
                >
                  <RefreshCw
                    className={cn(
                      'h-4 w-4',
                      activityAutoRefresh && activityFetching && 'animate-spin'
                    )}
                  />
                  {activityAutoRefresh ? 'Auto-Refresh On' : 'Auto-Refresh Off'}
                </button>
              </div>

              {/* Sound Toggle */}
              <div>
                <button
                  type="button"
                  onClick={() => setSoundEnabled(!soundEnabled)}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                    soundEnabled
                      ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                      : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                  )}
                >
                  {soundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
                  {soundEnabled ? 'Sound On' : 'Sound Off'}
                </button>
              </div>

              {/* Browser Notifications Toggle */}
              <div>
                {notificationPermission === 'granted' ? (
                  <button
                    type="button"
                    onClick={() => setBrowserNotificationsEnabled(!browserNotificationsEnabled)}
                    className={cn(
                      'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                      browserNotificationsEnabled
                        ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                        : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                    )}
                  >
                    {browserNotificationsEnabled ? (
                      <Bell className="h-4 w-4" />
                    ) : (
                      <BellOff className="h-4 w-4" />
                    )}
                    {browserNotificationsEnabled ? 'Alerts On' : 'Alerts Off'}
                  </button>
                ) : notificationPermission === 'denied' ? (
                  <button
                    type="button"
                    disabled
                    className="flex cursor-not-allowed items-center gap-2 rounded-lg border border-gray-300 bg-gray-100 px-4 py-2.5 text-sm font-medium text-gray-400"
                    title="Browser notifications are blocked. Enable them in your browser settings."
                  >
                    <BellOff className="h-4 w-4" />
                    Blocked
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={requestNotificationPermission}
                    className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    <Bell className="h-4 w-4" />
                    Enable Alerts
                  </button>
                )}
              </div>

              {/* Export CSV Button */}
              <div>
                <button
                  type="button"
                  onClick={exportActivityToCSV}
                  disabled={!activityData?.trades || activityData.trades.length === 0}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
                    activityData?.trades && activityData.trades.length > 0
                      ? 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                      : 'cursor-not-allowed border border-gray-200 bg-gray-100 text-gray-400'
                  )}
                >
                  <Download className="h-4 w-4" />
                  Export CSV
                </button>
              </div>
            </div>

            {/* Activity Table */}
            <DataTable
              data={activityData?.trades ?? []}
              columns={activityColumns}
              loading={activityLoading}
              emptyMessage="No recent trades from tracked traders"
            />

            {/* Activity Results Count */}
            {activityData && !activityLoading && activityData.trades.length > 0 && (
              <div className="mt-4 text-center text-sm text-gray-500">
                Showing {activityData.trades.length} recent trade
                {activityData.trades.length !== 1 ? 's' : ''}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Results Count */}
      {data && data.trackedTraders.length > 0 && (
        <div className="text-center text-sm text-gray-500">
          Tracking {data.trackedTraders.length} trader{data.trackedTraders.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
}
