import { Link, useParams } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { Card } from '@/components/ui/Card'
import { Timeline } from '@/components/ui/Timeline'
import { mockRequestDetail } from '@/data/mockRequestDetail'
import {
  STATUS_HISTORY_LABELS,
  mockStatusHistory,
} from '@/data/mockStatusHistory'

/**
 * Track Request Status (`/requests/:id/status`). Post-login page, so it uses
 * AppShell. Read-only: no forms, no validation, no network calls (design.md
 * per-page data strategy, requirements.md section 6, tasks.md Task 6).
 *
 * Per design.md's per-page data strategy this page always renders the one
 * hardcoded status_history from data/mockStatusHistory.ts and ignores the `:id`
 * in the URL for data. The param is read only so the "Back to request details"
 * link stays pointed at the URL the user came from (fallback: the mock's id).
 *
 * The history array is already oldest-first, which is the order the Timeline
 * draws top to bottom (chronological). Entries with a timestamp are reached
 * (filled dot); entries still pending have a null timestamp (hollow dot).
 *
 * Layout: bounded to the 720px detail-view width and centered in the content
 * area per design-tokens.md "Content width" (the shared .content-detail class).
 * AppShell owns the surrounding padding.
 */
export default function RequestStatusPage() {
  const { id } = useParams()
  const requestId = id ?? mockRequestDetail.id

  const steps = mockStatusHistory.map((entry) => ({
    label: STATUS_HISTORY_LABELS[entry.status],
    meta: entry.timestamp ?? 'Pending',
    filled: entry.timestamp !== null,
  }))

  return (
    <AppShell>
      <div className="content-detail flex flex-col gap-6">
        <header className="flex flex-col gap-2">
          <p className="text-dense text-text-secondary">
            Request #{requestId} · {mockRequestDetail.title}
          </p>
          <h1 className="text-h2 font-semibold text-text-primary">
            Status history
          </h1>
        </header>

        <Card>
          <Timeline steps={steps} />
        </Card>

        <Link
          to={`/requests/${requestId}`}
          className="text-dense font-semibold text-accent hover:underline"
        >
          Back to request details
        </Link>
      </div>
    </AppShell>
  )
}
