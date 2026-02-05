import * as React from 'react';
import {
  BarChart3,
  Brain,
  Anchor,
  AlertTriangle,
  TrendingUp,
  ChevronDown,
  LogIn,
  LogOut,
  Settings,
  Sparkles,
  Activity,
  PieChart,
  Wallet,
  Eye,
  Menu,
  X,
  Filter,
  Map,
  Trophy,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export type UserTier = 'FREE' | 'PRO';

export interface User {
  email: string;
  name?: string;
  tier: UserTier;
}

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

const navigationSections: NavSection[] = [
  {
    label: 'Markets',
    items: [
      { label: 'All Markets', href: '/markets', icon: BarChart3 },
      { label: 'Trending', href: '/markets/trending', icon: TrendingUp },
      { label: 'Categories', href: '/markets/categories', icon: PieChart },
      { label: 'Market Screener', href: '/screener', icon: Filter },
      { label: 'Market Map', href: '/market-map', icon: Map },
    ],
  },
  {
    label: 'Traders',
    items: [
      { label: 'Smart Scores', href: '/smart-scores', icon: Brain },
      { label: 'Whales', href: '/whales', icon: Anchor },
      { label: 'Leaderboard', href: '/pnl-leaderboard', icon: Trophy },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { label: 'Insider Detection', href: '/insiders', icon: AlertTriangle },
      { label: 'Market Activity', href: '/activity', icon: Activity },
      { label: 'Portfolio Tracker', href: '/portfolio', icon: Wallet },
    ],
  },
  {
    label: 'Watchlist',
    items: [
      { label: 'Tracked Traders', href: '/tracked-traders', icon: Eye },
      { label: 'Alerts', href: '/alerts', icon: Sparkles },
    ],
  },
];

export interface NavigationProps {
  user?: User | null;
  currentPath?: string;
  onSignOut?: () => void;
  className?: string;
}

export function Navigation({ user, currentPath = '/', onSignOut, className }: NavigationProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false);

  // Close mobile menu on Escape key
  React.useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMobileMenuOpen(false);
      }
    }

    if (mobileMenuOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [mobileMenuOpen]);

  return (
    <header className={cn('sticky top-0 z-50 w-full border-b border-gray-200 bg-white', className)}>
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <a href="/" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600">
            <BarChart3 className="h-5 w-5 text-white" />
          </div>
          <span className="text-lg font-semibold text-gray-900">HashDive</span>
        </a>

        {/* Navigation Dropdowns - Hidden on mobile */}
        <div className="hidden items-center gap-1 md:flex">
          {navigationSections.map((section) => (
            <NavDropdown key={section.label} section={section} currentPath={currentPath} />
          ))}
        </div>

        {/* Mobile menu button and Account Section */}
        <div className="flex items-center gap-2">
          {/* Mobile menu button - visible only on mobile */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="flex items-center justify-center rounded-lg p-2 text-gray-700 hover:bg-gray-100 md:hidden"
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
          >
            {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>

          {/* Account Section */}
          {user ? (
            <AccountDropdown user={user} onSignOut={onSignOut} />
          ) : (
            <a
              href="/login"
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
            >
              <LogIn className="h-4 w-4" />
              Log In
            </a>
          )}
        </div>
      </nav>

      {/* Mobile menu panel */}
      {mobileMenuOpen && (
        <div className="border-t border-gray-200 bg-white md:hidden">
          <div className="space-y-1 px-4 py-3">
            {navigationSections.map((section) => (
              <MobileNavSection
                key={section.label}
                section={section}
                currentPath={currentPath}
                onLinkClick={() => setMobileMenuOpen(false)}
              />
            ))}
          </div>
        </div>
      )}
    </header>
  );
}

interface NavDropdownProps {
  section: NavSection;
  currentPath: string;
}

function NavDropdown({ section, currentPath }: NavDropdownProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Close dropdown on Escape key
  React.useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  const hasActiveItem = section.items.some((item) => item.href === currentPath);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
          hasActiveItem ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700 hover:bg-gray-100'
        )}
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        {section.label}
        <ChevronDown className={cn('h-4 w-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <div className="absolute left-0 top-full z-10 mt-1 min-w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
          {section.items.map((item) => {
            const Icon = item.icon;
            const isActive = item.href === currentPath;

            return (
              <a
                key={item.href}
                href={item.href}
                onClick={() => setIsOpen(false)}
                className={cn(
                  'flex items-center gap-3 px-4 py-2 text-sm transition-colors',
                  isActive ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700 hover:bg-gray-50'
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface AccountDropdownProps {
  user: User;
  onSignOut?: () => void;
}

function AccountDropdown({ user, onSignOut }: AccountDropdownProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Close dropdown on Escape key
  React.useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  const handleSignOut = () => {
    setIsOpen(false);
    onSignOut?.();
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-700">
          {user.name?.[0]?.toUpperCase() || user.email[0]?.toUpperCase()}
        </div>
        <ChevronDown className={cn('h-4 w-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-10 mt-1 min-w-56 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
          {/* User info header */}
          <div className="border-b border-gray-100 px-4 py-3">
            <p className="text-sm font-medium text-gray-900">{user.name || user.email}</p>
            <p className="text-xs text-gray-500">{user.email}</p>
            <span
              className={cn(
                'mt-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium',
                user.tier === 'PRO' ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'
              )}
            >
              {user.tier === 'PRO' ? 'Pro' : 'Free'}
            </span>
          </div>

          {/* Menu items */}
          <div className="py-1">
            <a
              href="/settings"
              onClick={() => setIsOpen(false)}
              className="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              <Settings className="h-4 w-4" />
              Account Settings
            </a>

            {user.tier !== 'PRO' && (
              <a
                href="/upgrade"
                onClick={() => setIsOpen(false)}
                className="flex items-center gap-3 px-4 py-2 text-sm text-indigo-600 hover:bg-indigo-50"
              >
                <Sparkles className="h-4 w-4" />
                Upgrade to Pro
              </a>
            )}
          </div>

          {/* Sign out */}
          <div className="border-t border-gray-100 py-1">
            <button
              type="button"
              onClick={handleSignOut}
              className="flex w-full items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface MobileNavSectionProps {
  section: NavSection;
  currentPath: string;
  onLinkClick: () => void;
}

function MobileNavSection({ section, currentPath, onLinkClick }: MobileNavSectionProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);

  return (
    <div className="border-b border-gray-100 last:border-b-0">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between py-3 text-left text-sm font-medium text-gray-900"
        aria-expanded={isExpanded}
      >
        {section.label}
        <ChevronDown
          className={cn('h-4 w-4 text-gray-500 transition-transform', isExpanded && 'rotate-180')}
        />
      </button>

      {isExpanded && (
        <div className="pb-3 pl-4">
          {section.items.map((item) => {
            const Icon = item.icon;
            const isActive = item.href === currentPath;

            return (
              <a
                key={item.href}
                href={item.href}
                onClick={onLinkClick}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                  isActive ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700 hover:bg-gray-50'
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
