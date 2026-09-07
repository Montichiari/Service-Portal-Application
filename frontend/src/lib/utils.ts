import { type ClassValue, clsx } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * tailwind-merge only knows Tailwind's stock scales. Our custom token
 * utilities (styles/tokens.css → index.css @theme) share the `text-*`
 * prefix across two different concerns — font size (text-body, text-dense …)
 * and colour (text-on-fill, text-status-open …) — so without registering
 * them here, merging a size and a colour class drops one of them.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [
        { text: ['meta', 'dense', 'body', 'subhead', 'h3', 'h2', 'h1'] },
      ],
      'text-color': [
        {
          text: [
            'text-primary',
            'text-secondary',
            'on-fill',
            'chrome-text',
            'chrome-text-active',
            'accent',
            'danger',
            'status-open',
            'status-in-progress',
            'status-resolved',
            'status-closed',
            'status-draft',
            'priority-low',
            'priority-medium',
            'priority-high',
          ],
        },
      ],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
