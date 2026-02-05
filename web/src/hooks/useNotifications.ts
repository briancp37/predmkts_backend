/**
 * useNotifications Hook
 *
 * PRD #17 (Sprint 7) - Create reusable notification hook for tracked traders
 *
 * A reusable hook for managing browser notifications and sound alerts.
 * Used by Tracked Traders activity feed and Smart Trades Live pages.
 *
 * Features:
 * - Browser Notification API permission management
 * - Sound notification playback
 * - Settings persistence in localStorage
 * - Type-safe permission status tracking
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Storage keys for localStorage persistence
 */
const STORAGE_KEYS = {
  SOUND_ENABLED: 'notifications_sound_enabled',
  BROWSER_ENABLED: 'notifications_browser_enabled',
} as const;

/**
 * Notification options passed to showNotification
 */
export interface NotificationOptions {
  /** Optional icon URL for the notification */
  icon?: string;
  /** Optional tag to replace existing notifications with same tag */
  tag?: string;
  /** Whether the notification requires user interaction */
  requireInteraction?: boolean;
  /** Optional data to attach to the notification */
  data?: Record<string, unknown>;
}

/**
 * Return type for useNotifications hook
 */
export interface UseNotificationsReturn {
  /** Current notification permission status */
  permission: NotificationPermission;
  /** Whether sound notifications are enabled */
  soundEnabled: boolean;
  /** Whether browser notifications are enabled */
  browserNotificationsEnabled: boolean;
  /** Request notification permission from the user */
  requestPermission: () => Promise<NotificationPermission>;
  /** Show a browser notification (if permission granted) */
  showNotification: (
    title: string,
    body: string,
    options?: NotificationOptions
  ) => Notification | null;
  /** Play the notification sound */
  playSound: () => void;
  /** Toggle or set sound enabled state */
  setSoundEnabled: (enabled: boolean | ((prev: boolean) => boolean)) => void;
  /** Toggle or set browser notifications enabled state */
  setBrowserNotificationsEnabled: (enabled: boolean | ((prev: boolean) => boolean)) => void;
  /** Ref to attach to an audio element for sound playback */
  audioRef: React.RefObject<HTMLAudioElement | null>;
}

/**
 * Read a boolean value from localStorage
 */
function getStoredBoolean(key: string, defaultValue: boolean): boolean {
  if (typeof window === 'undefined') return defaultValue;
  try {
    const stored = localStorage.getItem(key);
    if (stored === null) return defaultValue;
    return stored === 'true';
  } catch {
    return defaultValue;
  }
}

/**
 * Write a boolean value to localStorage
 */
function setStoredBoolean(key: string, value: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(key, value.toString());
  } catch {
    // Ignore storage errors (e.g., private browsing mode)
  }
}

/**
 * Custom hook for managing notifications and sound alerts
 *
 * @example
 * ```tsx
 * const {
 *   permission,
 *   soundEnabled,
 *   browserNotificationsEnabled,
 *   requestPermission,
 *   showNotification,
 *   playSound,
 *   setSoundEnabled,
 *   setBrowserNotificationsEnabled,
 *   audioRef,
 * } = useNotifications();
 *
 * // In your component
 * <audio ref={audioRef} src="/notification.mp3" preload="auto" />
 *
 * // When a new event occurs
 * if (soundEnabled) playSound();
 * if (browserNotificationsEnabled) {
 *   showNotification('New Trade', 'Trader X bought $1000 on Market Y');
 * }
 * ```
 */
export function useNotifications(): UseNotificationsReturn {
  // Notification permission state
  const [permission, setPermission] = useState<NotificationPermission>('default');

  // Sound enabled state (persisted)
  const [soundEnabled, setSoundEnabledState] = useState(false);

  // Browser notifications enabled state (persisted)
  const [browserNotificationsEnabled, setBrowserNotificationsEnabledState] = useState(false);

  // Ref for audio element
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Initialize permission and persisted settings on mount
  useEffect(() => {
    // Check notification permission
    if (typeof window !== 'undefined' && 'Notification' in window) {
      setPermission(Notification.permission);
    }

    // Load persisted settings
    setSoundEnabledState(getStoredBoolean(STORAGE_KEYS.SOUND_ENABLED, false));
    setBrowserNotificationsEnabledState(getStoredBoolean(STORAGE_KEYS.BROWSER_ENABLED, false));
  }, []);

  /**
   * Request notification permission from the user
   * Returns the new permission status
   */
  const requestPermission = useCallback(async (): Promise<NotificationPermission> => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      return 'denied';
    }

    try {
      const result = await Notification.requestPermission();
      setPermission(result);

      // Auto-enable browser notifications if permission granted
      if (result === 'granted') {
        setBrowserNotificationsEnabledState(true);
        setStoredBoolean(STORAGE_KEYS.BROWSER_ENABLED, true);
      }

      return result;
    } catch {
      return 'denied';
    }
  }, []);

  /**
   * Show a browser notification
   * Returns the Notification object or null if unable to show
   */
  const showNotification = useCallback(
    (title: string, body: string, options?: NotificationOptions): Notification | null => {
      // Check if notifications are available and permitted
      if (typeof window === 'undefined' || !('Notification' in window)) {
        return null;
      }

      if (permission !== 'granted') {
        return null;
      }

      if (!browserNotificationsEnabled) {
        return null;
      }

      try {
        const notification = new Notification(title, {
          body,
          icon: options?.icon ?? '/icon.png',
          tag: options?.tag,
          requireInteraction: options?.requireInteraction ?? false,
          data: options?.data,
        });

        // Focus window when notification is clicked
        notification.onclick = () => {
          window.focus();
          notification.close();
        };

        return notification;
      } catch {
        // Notification creation can fail in some contexts
        return null;
      }
    },
    [permission, browserNotificationsEnabled]
  );

  /**
   * Play the notification sound
   * Uses the audio element attached via audioRef
   */
  const playSound = useCallback((): void => {
    if (!soundEnabled) return;
    if (!audioRef.current) return;

    // Reset to start and play
    audioRef.current.currentTime = 0;
    audioRef.current.play().catch(() => {
      // Ignore autoplay errors (e.g., user hasn't interacted with page yet)
    });
  }, [soundEnabled]);

  /**
   * Set sound enabled state (with persistence)
   */
  const setSoundEnabled = useCallback((enabled: boolean | ((prev: boolean) => boolean)): void => {
    setSoundEnabledState((prev) => {
      const newValue = typeof enabled === 'function' ? enabled(prev) : enabled;
      setStoredBoolean(STORAGE_KEYS.SOUND_ENABLED, newValue);
      return newValue;
    });
  }, []);

  /**
   * Set browser notifications enabled state (with persistence)
   */
  const setBrowserNotificationsEnabled = useCallback(
    (enabled: boolean | ((prev: boolean) => boolean)): void => {
      setBrowserNotificationsEnabledState((prev) => {
        const newValue = typeof enabled === 'function' ? enabled(prev) : enabled;
        setStoredBoolean(STORAGE_KEYS.BROWSER_ENABLED, newValue);
        return newValue;
      });
    },
    []
  );

  return {
    permission,
    soundEnabled,
    browserNotificationsEnabled,
    requestPermission,
    showNotification,
    playSound,
    setSoundEnabled,
    setBrowserNotificationsEnabled,
    audioRef,
  };
}

export default useNotifications;
