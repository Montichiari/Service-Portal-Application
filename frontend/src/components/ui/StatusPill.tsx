import { cn } from '@/lib/utils'

/**
 * Maps a request status to its pill treatment. Callers pass only `status`;
 * the colour and filled/outline choice come from the status table in
 * specs/frontend-phase/design-tokens.md and are never chosen by the caller.
 *
 * Enum values mirror the convention the backend `statuses` field is expected
 * to use; no openapi.yaml exists in the repo yet to be authoritative.
 */
export type Status = 'open' | 'in_progress' | 'resolved' | 'closed' | 'draft'

const STATUS_CONFIG: Record<Status, { label: string; className: string }> = {
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
  draft: {
    label: 'Draft',
    className: 'border border-status-draft text-status-draft',
  },
}

export interface StatusPillProps {
  status: Status
  className?: string
}

export function StatusPill({ status, className }: StatusPillProps) {
  const config = STATUS_CONFIG[status]
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
