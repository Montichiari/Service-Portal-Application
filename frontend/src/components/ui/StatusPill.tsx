import type { StatusName } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * Maps a request status to its pill treatment. Callers pass only `status`;
 * the colour and filled/outline choice come from the status table in
 * specs/frontend-phase/design-tokens.md and are never chosen by the caller.
 *
 * `StatusName` is imported from lib/api.ts rather than declared here (T-SR-1):
 * the four values are the backend's locked enum, seeded by a migration, so the
 * wire contract owns the vocabulary and this file owns only how it looks. The
 * prototype's fifth value, `draft`, is gone — it never existed server-side.
 *
 * The display labels live here and nowhere else (design.md §0 decision 4 makes
 * label mapping a frontend concern). Status names arrive from the API as raw
 * identifiers — `in_progress`, not 'In progress' — so this table is what turns
 * them into prose. Don't add a second mapping elsewhere.
 */
const STATUS_CONFIG: Record<StatusName, { label: string; className: string }> = {
  open: { label: 'Open', className: 'bg-status-open text-on-fill' },
  in_progress: {
    label: 'In progress',
    className: 'bg-status-in-progress text-on-fill',
  },
  resolved: { label: 'Resolved', className: 'bg-status-resolved text-on-fill' },
  closed: {
    label: 'Closed',
    className: 'border border-status-closed text-status-closed',
  },
}

/**
 * For a name this table doesn't know.
 *
 * Unreachable through the type system, but the `statuses` table is data a
 * migration seeds rather than a constant this build compiles: a fifth row
 * added server-side would arrive here typed as one of four and index to
 * `undefined`, taking down the render of every row that has it. Showing the
 * raw name in neutral chrome is a visible oddity; a blank dashboard is a
 * mystery. This is a backstop, not a fifth status — the table above still
 * carries exactly the four the backend defines.
 */
function configFor(status: StatusName) {
  return (
    STATUS_CONFIG[status] ?? {
      label: status,
      className: 'border border-status-closed text-status-closed',
    }
  )
}

export interface StatusPillProps {
  status: StatusName
  className?: string
}

export function StatusPill({ status, className }: StatusPillProps) {
  const config = configFor(status)
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
