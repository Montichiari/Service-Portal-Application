import type { Priority } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * Maps a request priority to its pill treatment. Same contract as StatusPill:
 * the caller passes only `priority`; colour and filled/outline come from the
 * priority palette in specs/frontend-phase/design-tokens.md. A distinct hue
 * pairing from status keeps the two from being confused at a glance.
 *
 * `Priority` comes from lib/api.ts (T-SR-1) — it is a wire value fixed by
 * SR-4's CHECK constraint, so the contract owns it and this file owns only how
 * it looks. Unlike status, the set is static in code rather than a lookup
 * table, which is why the filter dropdown hardcodes these three and fetches
 * the statuses.
 */
const PRIORITY_CONFIG: Record<Priority, { label: string; className: string }> = {
  low: {
    label: 'Low',
    className: 'border border-priority-low text-priority-low',
  },
  medium: {
    label: 'Medium',
    className: 'border border-priority-medium text-priority-medium',
  },
  high: { label: 'High', className: 'bg-priority-high text-on-fill' },
}

export interface PriorityPillProps {
  priority: Priority
  className?: string
}

export function PriorityPill({ priority, className }: PriorityPillProps) {
  const config = PRIORITY_CONFIG[priority]
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-card px-2 py-0.5 text-dense font-semibold whitespace-nowrap',
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  )
}
