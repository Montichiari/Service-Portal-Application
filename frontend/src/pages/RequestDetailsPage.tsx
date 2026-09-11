import { Link, useParams } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { AsyncSection } from '@/components/ui/AsyncSection'
import { Card } from '@/components/ui/Card'
import { PriorityPill } from '@/components/ui/PriorityPill'
import { StatusPill } from '@/components/ui/StatusPill'
import { Timestamp } from '@/components/ui/Timestamp'
import { getServiceRequest } from '@/lib/api'
import { useAsyncData } from '@/lib/async'
import { fullName } from '@/lib/names'

/**
 * View Request Details (`/requests/:id`) — wired to
 * `GET /service-requests/{id}` in T-SR-1, replacing the single hardcoded
 * mockRequestDetail object.
 *
 * The `:id` in the URL is now the request that gets fetched, which closes
 * frontend-contract.md §3.7: the prototype rendered the same object whatever
 * the URL said, so every request in the list led to one identical page. A
 * request the caller may not see comes back `404` (SR-12) — indistinguishable
 * from one that doesn't exist, by design, since leaking existence to someone
 * who can't read it is the thing SR-13 prevents — and that lands on the
 * visible not-found panel below rather than silently rendering something else.
 *
 * Comments are deliberately absent. The prototype embedded them on the mock
 * object; design.md §0 decision 3 makes them a sub-resource with their own
 * endpoint, and T-CM-1 builds the list and the composer. Rendering the
 * prototype's two fixed comments against a real request would have been a lie
 * with a real user's name on it.
 *
 * Layout: bounded to the 720px detail-view width and centered per
 * design-tokens.md "Content width" (the shared .content-detail class).
 * AppShell owns the surrounding padding.
 */
const REQUEST_TYPE_LABELS: Record<string, string> = { general: 'General' }

export default function RequestDetailsPage() {
  const { id } = useParams()
  // `id` is always present — the route pattern that mounts this page declares
  // it — but useParams cannot know that, and `''` fetches a malformed id,
  // which SR-13 answers with the same 404 as any other miss.
  const requestId = id ?? ''

  const request = useAsyncData(
    (signal) => getServiceRequest(requestId, signal),
    [requestId],
  )

  // A 404 is an answer about this request, not a failure to reach the server,
  // so it gets its own panel rather than AsyncSection's error banner — which
  // would otherwise render the API's bare "Not found." where the user needs to
  // know their link is wrong.
  if (request.status === 'error' && request.error.code === 'NOT_FOUND') {
    return (
      <AppShell>
        <div className="content-detail flex flex-col gap-6">
          <header className="flex flex-col gap-1">
            <h1 className="text-h2 font-semibold text-text-primary">
              Request not found
            </h1>
            <p className="text-dense text-text-secondary">
              This request doesn’t exist, or it isn’t one you have access to.
            </p>
          </header>
          <Link
            to="/"
            className="self-start text-dense font-semibold text-accent hover:underline"
          >
            Back to your requests
          </Link>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="content-detail flex flex-col gap-6">
        <AsyncSection state={request} loadingLabel="Loading request…">
          {(data) => (
            <div className="flex flex-col gap-6">
              <header className="flex flex-col gap-2">
                {/*
                 * The full UUID, not a short `#4271`-style number — design.md
                 * §0 decision 8 declined the `ticket_number` column, so this
                 * id is the only identifier the API exposes.
                 */}
                <p className="text-dense break-all text-text-secondary">
                  Request {data.id}
                </p>
                <h1 className="text-h2 font-semibold text-text-primary">
                  {data.title}
                </h1>
              </header>

              <Card>
                <h2 className="text-subhead font-semibold text-text-primary">
                  Details
                </h2>
                <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-3 text-body">
                  <dt className="text-text-secondary">Status</dt>
                  <dd>
                    <StatusPill status={data.status.name} />
                  </dd>

                  <dt className="text-text-secondary">Type</dt>
                  <dd className="text-text-primary">
                    {REQUEST_TYPE_LABELS[data.request_type] ?? data.request_type}
                  </dd>

                  <dt className="text-text-secondary">Priority</dt>
                  <dd>
                    <PriorityPill priority={data.priority} />
                  </dd>

                  <dt className="text-text-secondary">Requested by</dt>
                  <dd className="text-text-primary">{fullName(data.requestor)}</dd>

                  <dt className="text-text-secondary">Assigned to</dt>
                  <dd className="text-text-primary">
                    {/*
                     * Always "Unassigned" this phase: there is no assignment
                     * path and PATCH is deferred (design.md §7). Shown rather
                     * than hidden so the field's existence is honest — and
                     * never filled with an invented placeholder name.
                     */}
                    {data.assignee === null
                      ? 'Unassigned'
                      : fullName(data.assignee)}
                  </dd>

                  <dt className="text-text-secondary">Submitted</dt>
                  <dd className="text-text-primary">
                    <Timestamp value={data.created_at} withTime />
                  </dd>

                  <dt className="text-text-secondary">Last updated</dt>
                  <dd className="text-text-primary">
                    <Timestamp value={data.updated_at} withTime />
                  </dd>
                </dl>
                <Link
                  to={`/requests/${data.id}/status`}
                  className="text-dense font-semibold text-accent hover:underline"
                >
                  View full history
                </Link>
              </Card>

              <Card>
                <h2 className="text-subhead font-semibold text-text-primary">
                  Description
                </h2>
                <p className="text-body whitespace-pre-line text-text-primary">
                  {data.description}
                </p>
              </Card>
            </div>
          )}
        </AsyncSection>
      </div>
    </AppShell>
  )
}
