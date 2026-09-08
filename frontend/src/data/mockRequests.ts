import type { Status } from '@/components/ui/StatusPill'

/**
 * Hardcoded Requests Dashboard data — there is no backend in this phase
 * (frontend/CLAUDE.md "Non-goals for this phase"). Statuses deliberately
 * span all four request states from design-tokens.md (open, in_progress,
 * resolved, closed) so StatusPill's full colour range is visible on one
 * screen, per requirements.md section 4 / tasks.md Task 5.
 *
 * `lastUpdated` is a pre-formatted display string, not a timestamp — Task 5
 * calls for hardcoded relative-time strings, and there is no real event to
 * derive one from this phase.
 */
export interface MockRequest {
  id: string
  title: string
  status: Status
  lastUpdated: string
}

export const mockRequests: MockRequest[] = [
  {
    id: '4271',
    title: 'Laptop request for new starter',
    status: 'open',
    lastUpdated: '2h ago',
  },
  {
    id: '4268',
    title: 'VPN access for remote contractor',
    status: 'in_progress',
    lastUpdated: '6h ago',
  },
  {
    id: '4259',
    title: 'Password reset for finance shared mailbox',
    status: 'resolved',
    lastUpdated: '1d ago',
  },
  {
    id: '4245',
    title: 'Monitor replacement — flickering display',
    status: 'closed',
    lastUpdated: '5d ago',
  },
  {
    id: '4238',
    title: 'Offboarding — revoke access for M. Adeyemi',
    status: 'in_progress',
    lastUpdated: '1w ago',
  },
]
