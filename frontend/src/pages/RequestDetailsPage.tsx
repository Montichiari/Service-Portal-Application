import { Link, useParams } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { Card } from '@/components/ui/Card'
import { PriorityPill } from '@/components/ui/PriorityPill'
import { StatusPill } from '@/components/ui/StatusPill'
import { mockRequestDetail } from '@/data/mockRequestDetail'

/**
 * View Request Details (`/requests/:id`). Post-login page, so it uses AppShell.
 * Read-only: no forms, no validation, no network calls (design.md per-page data
 * strategy, requirements.md section 5, tasks.md Task 6).
 *
 * Per design.md's per-page data strategy this page always renders the one
 * hardcoded request from data/mockRequestDetail.ts and ignores the `:id` in the
 * URL for data — it does NOT look a request up from data/mockRequests.ts. The
 * param is read only so the in-app links stay pointed at the URL the user is
 * actually on (with a fallback to the mock's own id).
 *
 * Layout: bounded to the 720px detail-view width and centered in the content
 * area per design-tokens.md "Content width" (the shared .content-detail class).
 * AppShell owns the surrounding padding.
 */
const REQUEST_TYPE_LABELS = { general: 'General' } as const

export default function RequestDetailsPage() {
  const { id } = useParams()
  const request = mockRequestDetail
  const requestId = id ?? request.id

  return (
    <AppShell>
      <div className="content-detail flex flex-col gap-6">
        <header className="flex flex-col gap-2">
          <p className="text-dense text-text-secondary">Request #{requestId}</p>
          <h1 className="text-h2 font-semibold text-text-primary">
            {request.title}
          </h1>
        </header>

        <Card>
          <h2 className="text-subhead font-semibold text-text-primary">
            Details
          </h2>
          <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-3 text-body">
            <dt className="text-text-secondary">Status</dt>
            <dd>
              <StatusPill status={request.status} />
            </dd>

            <dt className="text-text-secondary">Type</dt>
            <dd className="text-text-primary">
              {REQUEST_TYPE_LABELS[request.request_type]}
            </dd>

            <dt className="text-text-secondary">Priority</dt>
            <dd>
              <PriorityPill priority={request.priority} />
            </dd>

            <dt className="text-text-secondary">Submitted</dt>
            <dd className="text-text-primary">{request.submittedDate}</dd>
          </dl>
          <Link
            to={`/requests/${requestId}/status`}
            className="text-dense font-semibold text-accent hover:underline"
          >
            View full history
          </Link>
        </Card>

        <Card>
          <h2 className="text-subhead font-semibold text-text-primary">
            Description
          </h2>
          <p className="text-body text-text-primary">{request.description}</p>
        </Card>

        <section className="flex flex-col gap-3">
          <h2 className="text-subhead font-semibold text-text-primary">
            Comments
          </h2>
          {/*
           * Read-only. There is deliberately no add-comment input or button on
           * this page — commenting is reserved for the separate admin-only page,
           * out of scope for these 6 demo pages (requirements.md section 5,
           * tasks.md Task 6).
           */}
          <ul className="flex flex-col gap-3">
            {request.comments.map((comment, index) => (
              <li key={index}>
                <Card className="gap-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <span className="text-dense font-semibold text-text-primary">
                      {comment.author}
                    </span>
                    <span className="text-meta text-text-secondary">
                      {comment.timestamp}
                    </span>
                  </div>
                  <p className="text-body text-text-primary">{comment.text}</p>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </AppShell>
  )
}
