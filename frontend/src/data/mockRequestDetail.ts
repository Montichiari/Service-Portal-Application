import type { Priority } from '@/components/ui/PriorityPill'
import type { Status } from '@/components/ui/StatusPill'

/**
 * Hardcoded View Request Details data — there is no backend in this phase
 * (frontend/CLAUDE.md "Non-goals"). design.md's per-page data strategy: this
 * page renders one fixed request object regardless of the `:id` in the URL.
 *
 * Kept consistent with the Requests Dashboard (data/mockRequests.ts): this is
 * request 4268, "VPN access for remote contractor", still `in_progress` — the
 * same row a user would have clicked to get here. Its status_history lives in
 * data/mockStatusHistory.ts and drives the Track Request Status page.
 *
 * `request_type` is fixed to "general" for the whole demo, mirroring the
 * disabled Request type field on the Submit Service Request form
 * (requirements.md section 3). Dates and comment timestamps are pre-formatted
 * display strings — there is no real event to derive them from this phase.
 */
export interface RequestComment {
  author: string
  text: string
  timestamp: string
}

export interface MockRequestDetail {
  id: string
  title: string
  status: Status
  request_type: 'general'
  priority: Priority
  description: string
  submittedDate: string
  comments: RequestComment[]
}

export const mockRequestDetail: MockRequestDetail = {
  id: '4268',
  title: 'VPN access for remote contractor',
  status: 'in_progress',
  request_type: 'general',
  priority: 'high',
  submittedDate: '4 Sep 2026',
  description:
    'A contractor (Daniel Osei, joining the data-migration project on a ' +
    '3-month engagement) needs VPN access to reach the internal ticketing ' +
    'and file servers from a company-issued laptop. Access should be scoped ' +
    'to the project network segment only and expire at the end of the ' +
    'engagement. Manager approval from R. Whitfield is attached to the ' +
    'original email thread.',
  comments: [
    {
      author: 'Priya Nair — IT Service Desk',
      text:
        'Picked this up. Before I raise the VPN profile I need the contractor’s ' +
        'start date and the exact end date for the engagement so the account ' +
        'auto-expires. Can you confirm both?',
      timestamp: '4 Sep 2026, 14:10',
    },
    {
      author: 'Daniel Osei — Requester',
      text:
        'Start date is 8 Sep 2026, engagement ends 5 Dec 2026. Laptop asset ' +
        'tag is LAP-2291. Thanks.',
      timestamp: '5 Sep 2026, 09:22',
    },
  ],
}
