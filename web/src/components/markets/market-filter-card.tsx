'use client';

import * as React from 'react';
import { Info, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export type FilterCardColor = 'purple' | 'blue' | 'yellow' | 'green';

export interface MarketFilterCardProps {
  /** Label displayed on the card */
  label: string;
  /** Icon component to display */
  icon: React.ElementType;
  /** Color theme for the card */
  color: FilterCardColor;
  /** Minimum value for the filter */
  minValue: string;
  /** Maximum value for the filter */
  maxValue: string;
  /** Callback when min value changes */
  onMinChange: (value: string) => void;
  /** Callback when max value changes */
  onMaxChange: (value: string) => void;
  /** Description text shown on the back of the card */
  description: string;
  /** Optional placeholder for min input */
  minPlaceholder?: string;
  /** Optional placeholder for max input */
  maxPlaceholder?: string;
  /** Optional formatter for displayed values */
  formatValue?: (value: string) => string;
  /** Optional input type (default: 'text') */
  inputType?: 'text' | 'number';
}

const colorStyles: Record<FilterCardColor, {
  border: string;
  bg: string;
  iconBg: string;
  iconColor: string;
  inputBorder: string;
  inputFocus: string;
}> = {
  purple: {
    border: 'border-purple-200',
    bg: 'bg-purple-50/50',
    iconBg: 'bg-purple-100',
    iconColor: 'text-purple-600',
    inputBorder: 'border-purple-200',
    inputFocus: 'focus:border-purple-400 focus:ring-purple-400',
  },
  blue: {
    border: 'border-blue-200',
    bg: 'bg-blue-50/50',
    iconBg: 'bg-blue-100',
    iconColor: 'text-blue-600',
    inputBorder: 'border-blue-200',
    inputFocus: 'focus:border-blue-400 focus:ring-blue-400',
  },
  yellow: {
    border: 'border-yellow-200',
    bg: 'bg-yellow-50/50',
    iconBg: 'bg-yellow-100',
    iconColor: 'text-yellow-600',
    inputBorder: 'border-yellow-200',
    inputFocus: 'focus:border-yellow-400 focus:ring-yellow-400',
  },
  green: {
    border: 'border-green-200',
    bg: 'bg-green-50/50',
    iconBg: 'bg-green-100',
    iconColor: 'text-green-600',
    inputBorder: 'border-green-200',
    inputFocus: 'focus:border-green-400 focus:ring-green-400',
  },
};

export function MarketFilterCard({
  label,
  icon: Icon,
  color,
  minValue,
  maxValue,
  onMinChange,
  onMaxChange,
  description,
  minPlaceholder = 'Min',
  maxPlaceholder = 'Max',
  inputType = 'text',
}: MarketFilterCardProps) {
  const [isFlipped, setIsFlipped] = React.useState(false);
  const styles = colorStyles[color];

  const handleFlip = () => {
    setIsFlipped(!isFlipped);
  };

  return (
    <div className="perspective-1000 h-[140px] w-full">
      <div
        className={cn(
          'relative h-full w-full transition-transform duration-[600ms] ease-in-out',
          'transform-style-preserve-3d',
          isFlipped && 'rotate-y-180'
        )}
        style={{
          transformStyle: 'preserve-3d',
          transform: isFlipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
        }}
      >
        {/* Front Side */}
        <div
          className={cn(
            'absolute inset-0 rounded-lg border p-4',
            'backface-hidden',
            styles.border,
            styles.bg
          )}
          style={{ backfaceVisibility: 'hidden' }}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <div className={cn('rounded-lg p-2', styles.iconBg)}>
                <Icon className={cn('h-4 w-4', styles.iconColor)} />
              </div>
              <span className="text-sm font-medium text-gray-700">{label}</span>
            </div>
            <button
              type="button"
              onClick={handleFlip}
              className="rounded-full p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
              aria-label={`Show ${label} filter description`}
            >
              <Info className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-4 flex items-center gap-2">
            <input
              type={inputType}
              value={minValue}
              onChange={(e) => onMinChange(e.target.value)}
              placeholder={minPlaceholder}
              className={cn(
                'w-full rounded-md border bg-white px-3 py-2 text-sm',
                'focus:outline-none focus:ring-1',
                styles.inputBorder,
                styles.inputFocus
              )}
              aria-label={`Minimum ${label}`}
            />
            <span className="text-gray-400">-</span>
            <input
              type={inputType}
              value={maxValue}
              onChange={(e) => onMaxChange(e.target.value)}
              placeholder={maxPlaceholder}
              className={cn(
                'w-full rounded-md border bg-white px-3 py-2 text-sm',
                'focus:outline-none focus:ring-1',
                styles.inputBorder,
                styles.inputFocus
              )}
              aria-label={`Maximum ${label}`}
            />
          </div>
        </div>

        {/* Back Side */}
        <div
          className={cn(
            'absolute inset-0 rounded-lg border p-4',
            'backface-hidden rotate-y-180',
            styles.border,
            styles.bg
          )}
          style={{
            backfaceVisibility: 'hidden',
            transform: 'rotateY(180deg)',
          }}
        >
          <div className="flex h-full flex-col">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <div className={cn('rounded-lg p-2', styles.iconBg)}>
                  <Icon className={cn('h-4 w-4', styles.iconColor)} />
                </div>
                <span className="text-sm font-medium text-gray-700">{label}</span>
              </div>
              <button
                type="button"
                onClick={handleFlip}
                className="rounded-full p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                aria-label="Close description"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="mt-3 flex-1 text-sm text-gray-600">{description}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default MarketFilterCard;
