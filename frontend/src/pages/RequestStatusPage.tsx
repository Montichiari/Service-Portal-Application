import { Link, useParams } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { Card } from '@/components/ui/Card'
import { Timeline } from '@/components/ui/Timeline'
import {
  STATUS_HISTORY_LABELS,
  mockStatusHistory,
} from '@/data/mockStatusHistory'

/**
 * Track Request Status (`/requests/:id/status`). Post-login page, so it uses
 * AppShell.
 *
 * **Still on prototype data, deliberately.** `T-SC-1` owns this page: it
 * replaces the fixed five-row template below by merging `GET /statuses`
 * against `GET /service-requests/{id}/status-changes` (design.md §5), and
 * retires `STATUS_HISTORY_LABELS` and the whole `StatusHistoryState`
 * vocabulary with it — the backend has four statuses and no `assigned` state,
 * and there is no assignment data behind that label at all.
 *
 * T-SR-1 touched this page for one reason only: it deleted
 * data/mockRequestDetail.ts, which this heading used for the request's title.
 * The title is gone rather than fetched — pulling the real request in here
 * would mean a real heading above an invented timeline, which reads as more
 * trustworthy than it is. The id comes from the URL, which is the one thing
 * this page legitimately knows until T-SC-1.
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
  const requestId = id ?? ''

  const steps = mockStatusHistory.map((entry) => ({
    label: STATUS_HISTORY_LABELS[entry.status],
    meta: entry.timestamp ?? 'Pending',
    filled: entry.timestamp !== null,
  }))

  return (
    <AppShell>
      <div className="content-detail flex flex-col gap-6">
        <header className="flex flex-col gap-2">
          <p className="text-dense break-all text-text-secondary">
            Request {requestId}
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
