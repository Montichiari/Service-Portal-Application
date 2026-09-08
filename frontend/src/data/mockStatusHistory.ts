/**
 * Hardcoded status_history for request 4268 (see data/mockRequestDetail.ts) —
 * the audit trail behind the Track Request Status page. No backend this phase
 * (frontend/CLAUDE.md "Non-goals"); design.md's per-page data strategy renders
 * this fixed array regardless of the `:id` in the URL.
 *
 * Entries are in chronological order (oldest first) — the order the Timeline
 * renders them top to bottom. A `timestamp` of `null` marks a step the request
 * has not reached yet: the page draws those as hollow Timeline dots and the
 * dated ones as filled. Request 4268 is `in_progress`, so submitted → assigned
 * → in_progress are reached and resolved → closed are still pending.
 *
 * `status` is the canonical audit value; STATUS_HISTORY_LABELS maps it to the
 * sentence-case label shown in the Timeline (design-tokens.md typography).
 */
export type StatusHistoryState =
  | 'submitted'
  | 'assigned'
  | 'in_progress'
  | 'resolved'
  | 'closed'

export interface StatusHistoryEntry {
  status: StatusHistoryState
  /** Pre-formatted display string, or null if this step is not yet reached. */
  timestamp: string | null
}

export const STATUS_HISTORY_LABELS: Record<StatusHistoryState, string> = {
  submitted: 'Submitted',
  assigned: 'Assigned to IT Service Desk',
  in_progress: 'In progress',
  resolved: 'Resolved',
  closed: 'Closed',
}

export const mockStatusHistory: StatusHistoryEntry[] = [
  { status: 'submitted', timestamp: '4 Sep 2026, 09:12' },
  { status: 'assigned', timestamp: '4 Sep 2026, 14:05' },
  { status: 'in_progress', timestamp: '8 Sep 2026, 06:30' },
  { status: 'resolved', timestamp: null },
  { status: 'closed', timestamp: null },
]
