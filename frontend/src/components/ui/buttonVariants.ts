import { cva } from 'class-variance-authority'

/**
 * Kept in its own module so Button.tsx exports only a component (fast-refresh
 * friendly). Import from here when styling a non-button element — e.g. a
 * router link — as a button.
 */
export const buttonVariants = cva(
  'inline-flex h-9 items-center justify-center gap-2 rounded-card px-4 text-body font-semibold whitespace-nowrap transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-on-fill hover:opacity-90',
        secondary:
          'border border-border bg-card text-text-primary hover:bg-surface',
      },
    },
    defaultVariants: {
      variant: 'primary',
    },
  },
)
